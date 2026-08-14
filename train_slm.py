"""
Train a small LSTM for next-word prediction and export to ONNX.

Architecture:
- Embedding layer (128-256 dim)
- 1-2 LSTM layers (128-256 hidden units)
- Linear output layer (vocabulary size)
- Trained on public domain English text
- Exported to ONNX for inference in NVDA add-on

Usage:
    python3 train_slm.py [--corpus-dir DIR] [--epochs N] [--embed-dim D] [--hidden-dim H]
"""

import argparse
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.onnx
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm


# ── Tokenization ──────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """Lowercase, keep contractions, split into words."""
    text = text.lower()
    # Replace smart quotes and dashes
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2014', ' ').replace('\u2013', ' ')
    return re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)*", text)


def load_gutenberg(filepath: str) -> str | None:
    """Load a Project Gutenberg text file, stripping boilerplate."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception:
        return None

    # Strip Gutenberg header/footer
    start_markers = [
        '*** START OF THE PROJECT GUTENBERG EBOOK',
        '*** START OF THIS PROJECT GUTENBERG EBOOK',
        '***START OF THE PROJECT GUTENBERG EBOOK',
    ]
    end_markers = [
        '*** END OF THE PROJECT GUTENBERG EBOOK',
        '*** END OF THIS PROJECT GUTENBERG EBOOK',
        '***END OF THE PROJECT GUTENBERG EBOOK',
    ]

    start_idx = -1
    for marker in start_markers:
        idx = text.find(marker)
        if idx != -1:
            start_idx = idx + len(marker)
            # Skip past the line
            newline = text.find('\n', start_idx)
            if newline != -1:
                start_idx = newline + 1
            break

    end_idx = len(text)
    for marker in end_markers:
        idx = text.find(marker)
        if idx != -1:
            end_idx = idx
            break

    if start_idx == -1:
        return None

    return text[start_idx:end_idx]


# ── Dataset ────────────────────────────────────────────────────────

class NextWordDataset(Dataset):
    """Sliding window dataset: given N context words, predict the next word."""

    def __init__(self, tokens: list[int], context_len: int = 4):
        self.tokens = tokens
        self.context_len = context_len
        # Each sample: tokens[i:i+context_len] -> tokens[i+context_len]
        self.n_samples = len(tokens) - context_len

    def __len__(self):
        return self.n_samples

    def __getitem__(self, idx):
        x = self.tokens[idx:idx + self.context_len]
        y = self.tokens[idx + self.context_len]
        return torch.tensor(x, dtype=torch.long), torch.tensor(y, dtype=torch.long)


# ── Model ─────────────────────────────────────────────────────────

class NextWordLSTM(nn.Module):
    def __init__(self, vocab_size: int, embed_dim: int = 128, hidden_dim: int = 128,
                 num_layers: int = 1, dropout: float = 0.2):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, num_layers,
                            batch_first=True, dropout=dropout if num_layers > 1 else 0)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_dim, vocab_size)

    def forward(self, x):
        # x: (batch, seq_len)
        emb = self.embedding(x)  # (batch, seq_len, embed_dim)
        lstm_out, _ = self.lstm(emb)  # (batch, seq_len, hidden_dim)
        last_out = lstm_out[:, -1, :]  # (batch, hidden_dim) — last timestep
        last_out = self.dropout(last_out)
        logits = self.fc(last_out)  # (batch, vocab_size)
        return logits


# ── Training ──────────────────────────────────────────────────────

def train_epoch(model, dataloader, optimizer, criterion, device):
    model.train()
    total_loss = 0
    n_batches = 0

    for x, y in tqdm(dataloader, desc="Training", leave=False):
        x, y = x.to(device), y.to(device)
        optimizer.zero_grad()
        logits = model(x)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1

    return total_loss / n_batches


@torch.no_grad()
def evaluate(model, dataloader, criterion, device):
    model.eval()
    total_loss = 0
    n_batches = 0
    correct = 0
    total = 0

    for x, y in tqdm(dataloader, desc="Evaluating", leave=False):
        x, y = x.to(device), y.to(device)
        logits = model(x)
        loss = criterion(logits, y)
        total_loss += loss.item()
        n_batches += 1
        preds = logits.argmax(dim=1)
        correct += (preds == y).sum().item()
        total += y.size(0)

    return total_loss / n_batches, correct / total


# ── ONNX Export ───────────────────────────────────────────────────

def export_onnx(model, vocab, context_len, embed_dim, output_path, device):
    """Export the trained model to ONNX format."""
    model.eval()
    # Create dummy input: batch_size=1, seq_len=context_len
    dummy_input = torch.zeros(1, context_len, dtype=torch.long).to(device)

    # Export
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        input_names=['input_ids'],
        output_names=['logits'],
        dynamic_axes={
            'input_ids': {0: 'batch_size'},
            'logits': {0: 'batch_size'},
        },
        opset_version=17,
    )
    print(f"Exported ONNX model to {output_path}")

    # Also save vocabulary
    vocab_path = output_path.replace('.onnx', '_vocab.json')
    with open(vocab_path, 'w') as f:
        json.dump({
            'word2idx': vocab['word2idx'],
            'context_len': context_len,
            'embed_dim': embed_dim,
        }, f)
    print(f"Saved vocabulary to {vocab_path}")


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Train SLM for WordPredictor")
    parser.add_argument('--corpus-dir', default='data/corpus',
                        help='Directory with .txt files')
    parser.add_argument('--epochs', type=int, default=5,
                        help='Number of training epochs')
    parser.add_argument('--embed-dim', type=int, default=128,
                        help='Embedding dimension')
    parser.add_argument('--hidden-dim', type=int, default=128,
                        help='LSTM hidden dimension')
    parser.add_argument('--num-layers', type=int, default=1,
                        help='Number of LSTM layers')
    parser.add_argument('--context-len', type=int, default=4,
                        help='Number of context words')
    parser.add_argument('--batch-size', type=int, default=256,
                        help='Training batch size')
    parser.add_argument('--lr', type=float, default=0.001,
                        help='Learning rate')
    parser.add_argument('--max-vocab', type=int, default=20000,
                        help='Maximum vocabulary size')
    parser.add_argument('--output', default='data/wordpredictor_slm.onnx',
                        help='Output ONNX model path')
    parser.add_argument('--device', default='auto',
                        help='Device: auto, cpu, cuda')
    args = parser.parse_args()

    # Device
    if args.device == 'auto':
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    else:
        device = torch.device(args.device)
    print(f"Using device: {device}")

    # ── Load corpus ────────────────────────────────────────────
    corpus_dir = Path(args.corpus_dir)
    if not corpus_dir.exists():
        print(f"Corpus directory {corpus_dir} not found. Downloading sample texts...")
        corpus_dir.mkdir(parents=True, exist_ok=True)
        download_sample_corpus(corpus_dir)

    print("Loading corpus...")
    all_tokens = []
    txt_files = sorted(corpus_dir.glob('*.txt'))
    if not txt_files:
        print("No .txt files found. Downloading sample texts...")
        download_sample_corpus(corpus_dir)
        txt_files = sorted(corpus_dir.glob('*.txt'))

    for fp in tqdm(txt_files, desc="Loading texts"):
        text = load_gutenberg(str(fp))
        if text:
            tokens = tokenize(text)
            all_tokens.extend(tokens)

    print(f"Total tokens: {len(all_tokens):,}")

    # ── Build vocabulary ──────────────────────────────────────
    word_counts = Counter(all_tokens)
    # Keep top N words, reserve 0 for padding, 1 for unknown
    top_words = ['<pad>', '<unk>'] + [w for w, _ in word_counts.most_common(args.max_vocab - 2)]
    word2idx = {w: i for i, w in enumerate(top_words)}
    idx2word = {i: w for w, i in word2idx.items()}
    vocab_size = len(word2idx)
    print(f"Vocabulary size: {vocab_size}")

    # Convert tokens to indices
    token_ids = [word2idx.get(t, 1) for t in all_tokens]  # 1 = <unk>

    # ── Create dataset ─────────────────────────────────────────
    dataset = NextWordDataset(token_ids, context_len=args.context_len)
    print(f"Training samples: {len(dataset):,}")

    # Split: 90% train, 10% validation
    split = int(0.9 * len(dataset))
    train_dataset = torch.utils.data.Subset(dataset, range(split))
    val_dataset = torch.utils.data.Subset(dataset, range(split, len(dataset)))

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False)

    # ── Build model ────────────────────────────────────────────
    model = NextWordLSTM(
        vocab_size=vocab_size,
        embed_dim=args.embed_dim,
        hidden_dim=args.hidden_dim,
        num_layers=args.num_layers,
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {n_params:,}")

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss(ignore_index=0)  # ignore padding

    # ── Train ──────────────────────────────────────────────────
    best_val_acc = 0
    for epoch in range(args.epochs):
        t0 = time.time()
        train_loss = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        elapsed = time.time() - t0

        print(f"Epoch {epoch+1}/{args.epochs} | "
              f"Train loss: {train_loss:.4f} | "
              f"Val loss: {val_loss:.4f} | "
              f"Val acc: {val_acc:.2%} | "
              f"Time: {elapsed:.1f}s")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            # Save checkpoint
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_acc': val_acc,
                'word2idx': word2idx,
                'args': vars(args),
            }, 'data/slm_checkpoint.pt')

    print(f"Best validation accuracy: {best_val_acc:.2%}")

    # ── Export ONNX ────────────────────────────────────────────
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    vocab = {'word2idx': word2idx, 'idx2word': idx2word}
    export_onnx(model, vocab, args.context_len, args.embed_dim, args.output, device)

    # ── Model size report ─────────────────────────────────────
    onnx_size = os.path.getsize(args.output)
    print(f"ONNX model size: {onnx_size:,} bytes ({onnx_size/1024/1024:.1f} MB)")


def download_sample_corpus(corpus_dir: Path):
    """Download a small set of public domain texts for training."""
    import urllib.request

    # A curated list of shorter, high-quality public domain texts
    gutenberg_ids = [
        11,     # Alice's Adventures in Wonderland
        1342,   # Pride and Prejudice
        1661,   # The Adventures of Sherlock Holmes
        2701,   # Moby Dick
        84,     # Frankenstein
        43,     # The Strange Case of Dr. Jekyll and Mr. Hyde
        345,    # Dracula
        174,    # The Picture of Dorian Gray
        98,     # A Tale of Two Cities
        1400,   # Great Expectations
        76,     # Adventures of Huckleberry Finn
        74,     # The Adventures of Tom Sawyer
        1260,   # Jane Eyre
        768,    # Wuthering Heights
        1184,   # The Count of Monte Cristo
        2600,   # War and Peace
        4300,   # Ulysses
        2814,   # Dubliners
        30254,  # The Way of All Flesh
        1399,   # Anna Karenina
        2554,   # Crime and Punishment
        28054,  # The Brothers Karamazov
        2147,   # The Works of Edgar Allan Poe — Volume 1
        2148,   # The Works of Edgar Allan Poe — Volume 2
        2149,   # The Works of Edgar Allan Poe — Volume 3
        2150,   # The Works of Edgar Allan Poe — Volume 4
        2151,   # The Works of Edgar Allan Poe — Volume 5
        158,    # Emma
        121,    # Northanger Abbey
        105,    # Persuasion
        141,    # Mansfield Park
        946,    # The Scarlet Letter
        408,    # The Souls of Black Folk
        244,    # A Study in Scarlet
        2097,   # The Hound of the Baskervilles
        1080,   # The Valley of Fear
        1635,   # The Sign of the Four
        120,    # Treasure Island
        16,     # Peter Pan
        1952,   # The Yellow Wallpaper
        15237,  # The Enchanted April
        19033,  # Ethan Frome
        219,    # The Awakening
        20203,  # Autobiography of Benjamin Franklin
        205,    # Walden
        1232,   # The Prince
        3300,   # An Inquiry into the Nature and Causes of the Wealth of Nations
        7370,   # Second Treatise of Government
        4705,   # The Federalist Papers
        829,    # Gulliver's Travels
        521,    # The Life and Adventures of Robinson Crusoe
        23,     # Narrative of the Life of Frederick Douglass
        1404,   # Up From Slavery
        4085,   # The Adventures of Roderick Random
        6593,   # History of Tom Jones, a Foundling
        2160,   # The Expedition of Humphry Clinker
        5197,   # My Life and Work (Henry Ford)
        2021,   # The Montessori Method
        24459,  # Democracy and Education
        852,    # The Island of Doctor Moreau
        5230,   # The War of the Worlds
        35,     # The Time Machine
        36,     # The Invisible Man
        1597,   # The Origin of Species
        1228,   # On the Origin of Species
        3825,   # Pragmatism
        5115,   # The Varieties of Religious Experience
        1497,   # The Republic
        5827,   # Thus Spake Zarathustra
        4363,   # Beyond Good and Evil
        19694,  # The Antichrist
        1998,   # Ecce Homo
        1934,   # Songs of Innocence and Experience
        1567,   # The Rime of the Ancient Mariner
        16389,  # The Enchiridion
        57333,  # Meditations (Marcus Aurelius, Long translation)
        2680,   # Meditations (Marcus Aurelius, Casaubon translation)
        29245,  # The Consolation of Philosophy
        1322,   # Leaves of Grass
        1632,   # The Autobiography of Charles Darwin
        103,    # Around the World in Eighty Days
        160,    # The Lost World
        139,    # The Sea-Wolf
        144,    # The Call of the Wild
        145,    # White Fang
        215,    # The Jungle
        20228,  # Noli Me Tangere
        673,    # El Filibusterismo
        1960,   # The Philippine Islands
        30295,  # The Social Cancer
        10681,  # The Reign of Greed
        2800,   # The House of Mirth
        241,    # The Custom of the Country
        284,    # The Age of Innocence
        11030,  # Summer
        4517,   # The Reef
        154,    # The Voyage Out
        24866,  # Night and Day
        89,     # Jacob's Room
        170,    # Mrs Dalloway
        29220,  # To the Lighthouse
        456,    # The Waves
        5670,   # Orlando
        21839,  # Flush
        289,    # The Years
        22566,  # Between the Acts
        218,    # The Return of the Native
        122,    # Far from the Madding Crowd
        599,    # Tess of the d'Urbervilles
        507,    # Jude the Obscure
        3049,   # The Mayor of Casterbridge
        325,    # Under the Greenwood Tree
        2875,   # A Pair of Blue Eyes
        3055,   # The Woodlanders
        110,    # The Hunchback of Notre Dame
        135,    # Les Miserables (vol 1)
        136,    # Les Miserables (vol 2)
        137,    # Les Miserables (vol 3)
        138,    # Les Miserables (vol 4)
        139,    # Les Miserables (vol 5)
        119,    # A Connecticut Yankee in King Arthur's Court
        86,     # The Prince and the Pauper
        3177,   # Pudd'nhead Wilson
        3186,   # The Mysterious Stranger
        91,     # Roughing It
        245,    # Life on the Mississippi
        3176,   # The Innocents Abroad
        142,    # The Importance of Being Earnest
        174,    # The Picture of Dorian Gray
        844,    # Lady Windermere's Fan
        790,    # An Ideal Husband
        885,    # A Woman of No Importance
        20612,  # De Profundis
        301,    # The Ballad of Reading Gaol
        33,     # The Scarlet Pimpernel
        60,     # I Will Repay
        61,     # The Elusive Pimpernel
        62,     # El Dorado
        63,     # Lord Tony's Wife
        64,     # The League of the Scarlet Pimpernel
        65,     # The Triumph of the Scarlet Pimpernel
        2000,   # Don Quixote (vol 1)
        5921,   # Don Quixote (vol 2)
        996,    # The Decameron
        8800,   # The Divine Comedy
        100,    # The Complete Works of William Shakespeare
        2264,   # Macbeth
        2265,   # Hamlet
        1513,   # Romeo and Juliet
        1533,   # Othello
        1524,   # King Lear
        1777,   # A Midsummer Night's Dream
        2242,   # The Tempest
        23042,  # Much Ado About Nothing
        1103,   # As You Like It
        1112,   # The Taming of the Shrew
        1120,   # Twelfth Night
        1130,   # The Merchant of Venice
        1522,   # Julius Caesar
        2253,   # Antony and Cleopatra
        1787,   # Richard III
        2257,   # Henry V
        1106,   # The Winter's Tale
        1532,   # Measure for Measure
        1531,   # Cymbeline
        1107,   # Coriolanus
        1108,   # Timon of Athens
        1109,   # Pericles
        1110,   # The Two Noble Kinsmen
        1505,   # Venus and Adonis
        1545,   # The Rape of Lucrece
        1546,   # The Sonnets
        1547,   # A Lover's Complaint
        1548,   # The Passionate Pilgrim
        1549,   # The Phoenix and the Turtle
    ]

    print(f"Downloading {len(gutenberg_ids)} texts from Project Gutenberg...")
    for gid in tqdm(gutenberg_ids):
        url = f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt"
        outpath = corpus_dir / f"pg{gid}.txt"
        if outpath.exists():
            continue
        try:
            urllib.request.urlretrieve(url, str(outpath))
        except Exception as e:
            print(f"  Failed to download {gid}: {e}")
        # Small delay to be polite
        import time
        time.sleep(0.1)

    print(f"Downloaded corpus to {corpus_dir}")


if __name__ == '__main__':
    main()
