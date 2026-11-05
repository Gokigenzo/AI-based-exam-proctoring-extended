from dataclasses import dataclass
import numpy as np


@dataclass
class AudioSegment:
    samples: np.ndarray
    start_sample: int
    end_sample: int
    continuation: bool = False


class Segmenter:
    """Input blocks must be contiguous 512-sample 16 kHz frames."""
    def __init__(self, sample_rate=16000, silence=.8, max_seconds=20, overlap=.5):
        self.rate = sample_rate
        self.silence_limit = int(silence * sample_rate)
        self.maximum = int(max_seconds * sample_rate)
        self.overlap = int(overlap * sample_rate)
        self.position = 0
        self.start = None
        self.blocks = []
        self.quiet = 0
        self.continuation = False

    def push(self, block, speech):
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        at = self.position
        self.position += len(block)
        if self.start is None:
            if not speech:
                return None
            self.start = at
        self.blocks.append(block.copy())
        self.quiet = 0 if speech else self.quiet + len(block)
        size = self.position - self.start
        if self.quiet >= self.silence_limit:
            return self.flush()
        if size >= self.maximum:
            samples = np.concatenate(self.blocks)
            segment = AudioSegment(samples, self.start, self.position, self.continuation)
            keep = samples[-self.overlap:]
            self.start = self.position - len(keep)
            self.blocks, self.quiet, self.continuation = [keep], 0, True
            return segment
        return None

    def flush(self):
        if self.start is None:
            return None
        samples = np.concatenate(self.blocks)
        result = AudioSegment(samples, self.start, self.start + len(samples), self.continuation)
        self.start, self.blocks, self.quiet, self.continuation = None, [], 0, False
        return result


def remove_overlap(previous, current, max_words=12):
    before, after = previous.split(), current.split()
    for size in range(min(max_words, len(before), len(after)), 0, -1):
        if [word.casefold().strip(".,!?:;") for word in before[-size:]] == [word.casefold().strip(".,!?:;") for word in after[:size]]:
            return " ".join(after[size:])
    return current


def speech_allowed(start, end, intervals):
    # Only fully covered speech suppresses the alert; partial overlap still needs review.
    return any(start >= interval[0] and end <= interval[1] for interval in intervals)
