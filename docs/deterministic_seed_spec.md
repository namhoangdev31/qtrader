# Deterministic Seeding Specification (DSS v1.0)

**Principal Goal**: Establish a verifiable, bit-perfect reproducibility chain across all execution trials.

## 1. Mathematical Entropy Model

The system operates on a tiered, cryptographic seed derivation approach to ensure that individual modules have unique but deterministic seeds.

### 1.1 Global Entropy Anchor ($S$)

The base seed is derived from execution-specific metadata using `SHA256`:

$$S = \text{int}(\text{SHA256}(strategy\_id + \text{"-"} + timestamp + \text{"-"} + env)[:8], 16)$$

- **Strategy ID**: Unique identifier for the alpha/execution strategy.
- **Timestamp**: ISO format start time for the trial (pinning the backtest).
- **Environment**: One of `{backtest, dev, live}`.

### 1.2 Module-Specific Derivation ($s_m$)

For modules requiring their own independent entropy (e.g., RL agents), we derive a sub-seed using a salt-based XOR:

$$s_m = (S \oplus \text{adler32}(module\_name)) \pmod{2^{32}}$$

## 2. Library Injection

The `SeedManager` is responsible for state injection into common stochastic libraries:

- **Python Native**: `random.seed(S)`
- **NumPy**: `np.random.seed(S)`
- **PyTorch**:
  - `torch.manual_seed(S)`
  - `torch.cuda.manual_seed_all(S)`
  - `torch.backends.cudnn.deterministic = True`
  - `torch.backends.cudnn.benchmark = False`

## 3. Deployment Constraints

1. **Immutability**: Once a seed state is applied to a process, it cannot be modified. Subsequent calls to `apply()` will be logged as warnings and ignored.
2. **No OS Entropy**: Modules MUST NOT use `os.urandom()` or `/dev/urandom` for trading logic.
3. **No Time-Based Randomness**: `random.seed(time.time())` is strictly forbidden.

## 4. Implementation Reference

The logic is encapsulated in `qtrader/core/seed_manager.py`. All strategies are required to initialize the `SeedManager` at the start of their lifecycle.
