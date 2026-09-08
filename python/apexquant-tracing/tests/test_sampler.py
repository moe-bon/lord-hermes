from apexquant_tracing.sampler import DeterministicSampler


def test_sampler_ratio_zero() -> None:
    sampler = DeterministicSampler(0.0)

    assert sampler.should_sample("0af7651916cd43dd8448eb211c80319c") is False


def test_sampler_ratio_one() -> None:
    sampler = DeterministicSampler(1.0)

    assert sampler.should_sample("0af7651916cd43dd8448eb211c80319c") is True


def test_sampler_is_deterministic() -> None:
    sampler = DeterministicSampler(0.5)

    trace_id = "0af7651916cd43dd8448eb211c80319c"

    first = sampler.should_sample(trace_id)
    second = sampler.should_sample(trace_id)

    assert first == second