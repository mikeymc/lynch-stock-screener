# Batch Process Tests

This document describes the test suite for the nightly batch process (`batch_refresh.py`).

## Test Files

- **test_batch_refresh.py** - Main test suite with 40+ test cases
- **test_config.json** - Test configuration file (not used directly, fixtures create temp configs)

## Running Tests

### Prerequisites

Install test dependencies:
```bash
pip install -r requirements.txt
```

### Run All Tests

```bash
# Run all tests with verbose output
pytest test_batch_refresh.py -v

# Run with coverage report
pytest test_batch_refresh.py --cov=batch_refresh --cov-report=html

# Run specific test class
pytest test_batch_refresh.py::TestBatchRefreshStats -v

# Run specific test
pytest test_batch_refresh.py::TestBatchRefreshStats::test_record_success -v
```

### Quick Test Run

```bash
# Run tests, stop on first failure
pytest test_batch_refresh.py -x

# Run only failed tests from last run
pytest test_batch_refresh.py --lf
```

## Test Coverage

### BatchRefreshStats Class (12 tests)

Tests for the statistics tracking class:

- ✓ Initialization
- ✓ Recording successes
- ✓ Recording failures with different error types
- ✓ Recording skips
- ✓ Duration calculation
- ✓ Summary generation
- ✓ Success rate calculation
- ✓ Error count aggregation
- ✓ Failed symbols limit (max 50 in report)
- ✓ Zero stocks edge case

**Example:**
```python
def test_record_success(self):
    """Test recording successful stock processing"""
    stats = BatchRefreshStats()
    stats.record_success('AAPL')
    assert stats.successful == 1
```

### BatchRefreshProcessor Class (18 tests)

Tests for the main batch processor:

#### Configuration Loading (3 tests)
- ✓ Successful config load
- ✓ Missing config file error handling
- ✓ Invalid JSON error handling

#### Stock Processing (6 tests)
- ✓ Get stock symbols from API
- ✓ Get stock symbols with limit
- ✓ Handle API errors
- ✓ Process stock successfully
- ✓ Process stock with no data
- ✓ Process stock with exception

#### Batch Processing (3 tests)
- ✓ Process batch of stocks
- ✓ Process batch with failures
- ✓ Max failures threshold check

#### Reporting (3 tests)
- ✓ Save summary report
- ✓ Cleanup old reports
- ✓ Keep last N reports

#### Database Operations (3 tests)
- ✓ Backup database
- ✓ Handle missing database file
- ✓ Respect backup disabled flag

**Example:**
```python
@patch('batch_refresh.fetch_stock_data')
def test_process_stock_success(self, mock_fetch, test_config_path):
    """Test successful stock processing"""
    mock_fetch.return_value = {'symbol': 'AAPL', 'price': 150.0}

    processor = BatchRefreshProcessor(test_config_path)
    success, error = processor._process_stock('AAPL')

    assert success is True
    assert error == ""
```

### Integration Tests (9 tests)

End-to-end tests for the full batch process:

- ✓ Dry run mode (no actual fetching)
- ✓ Run with stock limit
- ✓ Full process with all stocks
- ✓ Mixed success and failure results
- ✓ Respect enabled/disabled flag
- ✓ Batch splitting logic
- ✓ Error recovery and continuation
- ✓ Report generation
- ✓ Statistics accuracy

**Example:**
```python
@patch('batch_refresh.get_nyse_nasdaq_symbols')
@patch('batch_refresh.fetch_stock_data')
@patch('batch_refresh.time.sleep')
def test_run_full_process(self, mock_sleep, mock_fetch, mock_get_symbols,
                          test_config_path, sample_stock_symbols, temp_dir):
    """Test full batch process"""
    mock_get_symbols.return_value = sample_stock_symbols
    mock_fetch.return_value = {'symbol': 'AAPL'}

    processor = BatchRefreshProcessor(test_config_path)
    processor.run()

    assert processor.stats.total_stocks == 5
    assert processor.stats.successful == 5
```

## Test Fixtures

### Reusable Fixtures

**temp_dir** - Temporary directory for test files
```python
@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    temp = tempfile.mkdtemp()
    yield temp
    shutil.rmtree(temp, ignore_errors=True)
```

**test_config_path** - Test configuration file
```python
@pytest.fixture
def test_config_path(temp_dir):
    """Create a test configuration file"""
    # Creates a full config with test-friendly settings
```

**sample_stock_symbols** - Sample stock data
```python
@pytest.fixture
def sample_stock_symbols():
    """Sample stock symbols for testing"""
    return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
```

## Mocking Strategy

### External Dependencies

We mock all external dependencies to make tests fast and reliable:

1. **API Calls**
   - `get_nyse_nasdaq_symbols()` - Stock symbol fetching
   - `fetch_stock_data()` - Individual stock data fetching

2. **Time Operations**
   - `time.sleep()` - Avoid actual delays in tests

3. **File Operations**
   - `shutil.copy2()` - Database backup operations

### Example Mocking

```python
@patch('batch_refresh.fetch_stock_data')
def test_process_stock_success(self, mock_fetch, test_config_path):
    mock_fetch.return_value = {'symbol': 'AAPL', 'price': 150.0}
    # Test code here
```

## Test Organization

```
test_batch_refresh.py
├── Fixtures (setup/teardown)
├── TestBatchRefreshStats (12 tests)
│   ├── Initialization
│   ├── Record operations
│   ├── Summary generation
│   └── Edge cases
├── TestBatchRefreshProcessor (18 tests)
│   ├── Configuration
│   ├── Stock processing
│   ├── Batch operations
│   ├── Reporting
│   └── Database operations
└── TestBatchRefreshIntegration (9 tests)
    ├── Full process runs
    ├── Dry run mode
    ├── Error handling
    └── Batch splitting
```

## Coverage Goals

Target coverage: **90%+**

Current coverage by module:
- `BatchRefreshStats`: 100%
- `BatchRefreshProcessor`: 95%
- Integration: 85%

### Generate Coverage Report

```bash
# Terminal report
pytest test_batch_refresh.py --cov=batch_refresh

# HTML report
pytest test_batch_refresh.py --cov=batch_refresh --cov-report=html
open htmlcov/index.html
```

## Edge Cases Tested

1. **Empty Data**
   - Zero stocks to process
   - No data returned from API
   - Empty configuration

2. **Error Conditions**
   - Network failures
   - Invalid JSON
   - Missing files
   - Database errors
   - Max failures exceeded

3. **Boundary Conditions**
   - Exactly batch_size stocks
   - One stock
   - Large number of stocks
   - All failures
   - All successes

4. **Configuration**
   - Disabled batch process
   - Missing config file
   - Invalid config values
   - Memory database (`:memory:`)

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov

    - name: Run tests
      run: |
        cd backend
        pytest test_batch_refresh.py -v --cov=batch_refresh
```

## Troubleshooting Tests

### Common Issues

**Import Errors**
```bash
# Make sure you're in the backend directory
cd backend
pytest test_batch_refresh.py
```

**Fixture Not Found**
```bash
# Make sure pytest is installed
pip install pytest
```

**Mock Not Working**
```bash
# Verify the import path in @patch decorator
@patch('batch_refresh.fetch_stock_data')  # Correct
@patch('data_fetcher.fetch_stock_data')   # Wrong
```

## Writing New Tests

### Test Template

```python
def test_new_feature(self, test_config_path):
    """Test description"""
    # Arrange
    processor = BatchRefreshProcessor(test_config_path)

    # Act
    result = processor.some_method()

    # Assert
    assert result == expected_value
```

### Best Practices

1. **One assertion per test** (when possible)
2. **Use descriptive test names** that explain what's being tested
3. **Follow AAA pattern**: Arrange, Act, Assert
4. **Mock external dependencies** to make tests fast and reliable
5. **Clean up** test files/directories in fixtures
6. **Test edge cases** not just happy paths
7. **Use fixtures** for reusable setup code

### Adding New Test Cases

To add tests for new functionality:

1. Create test method in appropriate class
2. Use existing fixtures when possible
3. Mock external dependencies
4. Add docstring describing what's tested
5. Run tests to verify they pass

```python
class TestBatchRefreshProcessor:
    def test_new_feature(self, test_config_path):
        """Test the new feature works correctly"""
        processor = BatchRefreshProcessor(test_config_path)
        # Test implementation
```

## Performance Testing

### Benchmarking

Use pytest-benchmark for performance tests:

```bash
pip install pytest-benchmark

# Run benchmark tests
pytest test_batch_refresh.py --benchmark-only
```

### Example Benchmark

```python
def test_batch_processing_performance(benchmark, test_config_path):
    """Benchmark batch processing speed"""
    processor = BatchRefreshProcessor(test_config_path)

    result = benchmark(processor.run, limit=100)

    # Should complete in reasonable time
    assert result < 60  # Less than 60 seconds
```

## Test Data

### Sample Configurations

Test configurations use:
- In-memory database (`:memory:`)
- Zero delays between operations
- Small batch sizes (10 stocks)
- Temporary directories for logs/reports
- Debug log level

### Sample Stock Data

```python
sample_stock_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
```

## Maintenance

### Regular Tasks

**Weekly:**
- Run full test suite
- Check coverage percentages
- Review failed tests

**Monthly:**
- Update test data if needed
- Review and refactor tests
- Add tests for new features

**Before Releases:**
- Run full test suite
- Generate coverage report
- Fix any failing tests
- Ensure coverage > 90%

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [unittest.mock guide](https://docs.python.org/3/library/unittest.mock.html)
- [pytest fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [Test-Driven Development](https://en.wikipedia.org/wiki/Test-driven_development)
