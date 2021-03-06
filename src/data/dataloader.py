  
import json
import torch
import torch.utils.data as data


PAD_WORD = -1 

class ParallelDataset(data.Dataset):
    """Custom data.Dataset compatible with data.DataLoader."""
    def __init__(self, src_path, trg_path, src_word2id, trg_word2id):
        """Reads source and target sequences from txt files."""
        self.src_seqs = open(src_path).read().splitlines()
        self.trg_seqs = open(trg_path).read().splitlines()
        self.num_total_seqs = len(self.src_seqs)
        self.src_word2id = src_word2id
        self.trg_word2id = trg_word2id
        self.pad_index = src_word2id.index('<pad>')

    def __getitem__(self, index):
        """Returns one data pair (source and target)."""
        src_seq = self.src_seqs[index]
        trg_seq = self.trg_seqs[index]
        src_seq = self.preprocess(src_seq, self.src_word2id, trg=False)
        trg_seq = self.preprocess(trg_seq, self.trg_word2id)
        return src_seq, trg_seq

    def __len__(self):
        return self.num_total_seqs

    def preprocess(self, sequence, word2id, trg=True):
        """Converts words to ids."""
        tokens = sequence.split()
        sequence = []
        sequence.append(word2id.index('<s>'))
        sequence.extend([word2id.index(token) for token in tokens])
        sequence.append(word2id.index('</s>'))
        sequence = torch.Tensor(sequence)
        return sequence


def parallel_collate_fn(data):
    """Creates mini-batch tensors from the list of tuples (src_seq, trg_seq).
    We should build a custom collate_fn rather than using default collate_fn,
    because merging sequences (including padding) is not supported in default.
    Seqeuences are padded to the maximum length of mini-batch sequences (dynamic padding).
    Args:
        data: list of tuple (src_seq, trg_seq).
            - src_seq: torch tensor of shape (?); variable length.
            - trg_seq: torch tensor of shape (?); variable length.
    Returns:
        src_seqs: torch tensor of shape (batch_size, padded_length).
        src_lengths: list of length (batch_size); valid length for each padded source sequence.
        trg_seqs: torch tensor of shape (batch_size, padded_length).
        trg_lengths: list of length (batch_size); valid length for each padded target sequence.
    """
    def merge(sequences):
        lengths = [len(seq) for seq in sequences]
        padded_seqs = torch.zeros(len(sequences), max(lengths)).long().fill_(PAD_WORD)
        for i, seq in enumerate(sequences):
            end = lengths[i]
            padded_seqs[i, :end] = seq[:end]
        return padded_seqs, lengths

    # sort a list by sequence length (descending order) to use pack_padded_sequence
    data.sort(key=lambda x: len(x[0]), reverse=True)

    # seperate source and target sequences
    src_seqs, trg_seqs = zip(*data)

    # merge sequences (from tuple of 1D tensor to 2D tensor)
    src_seqs, src_lengths = merge(src_seqs)
    trg_seqs, trg_lengths = merge(trg_seqs)

    return src_seqs, src_lengths, trg_seqs, trg_lengths


def get_train_parallel_loader(src_path, trg_path, src_word2id, trg_word2id, batch_size, world_size, rank):
    """Returns data loader for custom dataset.
    Args:
        src_path: txt file path for source domain.
        trg_path: txt file path for target domain.
        src_word2id: word-to-id dictionary (source domain).
        trg_word2id: word-to-id dictionary (target domain).
        batch_size: mini-batch size.
    Returns:
        data_loader: data loader for custom dataset.
    """
    dataset = ParallelDataset(src_path, trg_path, src_word2id, trg_word2id)
    global PAD_WORD
    PAD_WORD = src_word2id.index('<pad>')

    sampler =  torch.utils.data.distributed.DistributedSampler(
        dataset,
        num_replicas=world_size,
        rank=rank
    )
    data_loader = torch.utils.data.DataLoader(dataset=dataset,
                                              batch_size=batch_size,
                                              collate_fn=parallel_collate_fn,
                                              sampler = sampler,
                                              )
    return data_loader, sampler

def get_valid_parallel_loader(src_path, trg_path, src_word2id, trg_word2id, batch_size):
    dataset = ParallelDataset(src_path, trg_path, src_word2id, trg_word2id)
    global PAD_WORD
    PAD_WORD = src_word2id.index('<pad>')
    data_loader = torch.utils.data.DataLoader(dataset=dataset,
                                              batch_size=batch_size,
                                              shuffle=False,
                                              collate_fn=parallel_collate_fn)
    return data_loader
                      