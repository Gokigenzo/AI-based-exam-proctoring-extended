"""Dependency-free per-update learning-rate schedule."""
import math


def update_early_stopping(epoch, start_epoch, value, best, stale, min_delta):
    if epoch < start_epoch:
        return min(best, value), 0
    if value < best - min_delta:
        return value, 0
    return best, stale + 1


def learning_rate(step, total_steps, warmup_steps, peak, minimum):
    if not 0 <= minimum <= peak or total_steps < 1 or not 0 <= warmup_steps < total_steps:
        raise ValueError('Invalid learning-rate schedule')
    if step < warmup_steps:
        return peak * (step + 1) / max(1, warmup_steps)
    progress = min(1., max(0., (step - warmup_steps) / max(1, total_steps - warmup_steps - 1)))
    return minimum + .5 * (peak - minimum) * (1 + math.cos(math.pi * progress))
