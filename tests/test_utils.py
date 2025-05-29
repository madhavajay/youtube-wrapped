import pytest
from unittest.mock import patch, mock_open, MagicMock, call as mock_call
from pathlib import Path
import pandas as pd
import json 

# Add project root to sys.path to allow importing utils
import sys
sys.path.append(str(Path(__file__).parent.parent))
from utils import YoutubeDataPipelineState

# Mock app_data_dir for tests
APP_DATA_DIR = Path("/fake/app_data")
CONFIG_FILE_PATH = APP_DATA_DIR / "cache" / "config.json"

# --- Test Initialization and Config Handling ---

def test_init_load_config_exists():
    """Test initialization when config.json exists."""
    mock_config_data = {"youtube-api-key": "fake_key", "processing": True}
    
    # This mock factory helps direct Path().exists() calls
    def path_exists_side_effect(path_obj_instance):
        if path_obj_instance == CONFIG_FILE_PATH:
            return True # config.json exists
        # For other paths that might be checked during init (e.g. data files if any logic changes)
        return False 

    # Mock open for reading config.json
    m_open = mock_open(read_data=json.dumps(mock_config_data))
    
    # Patch Path.exists in the 'utils' module where Path is used.
    # Patch builtins.open for file operations.
    with patch('utils.Path.exists', side_effect=path_exists_side_effect) as mock_path_exists, \
         patch('builtins.open', m_open) as mock_builtin_open:
        
        state = YoutubeDataPipelineState(APP_DATA_DIR)
        
        # Ensure Path.exists was called for CONFIG_FILE_PATH
        mock_path_exists.assert_any_call(CONFIG_FILE_PATH)
        
        # Ensure open was called to read CONFIG_FILE_PATH
        mock_builtin_open.assert_called_once_with(CONFIG_FILE_PATH, "r")
        
        assert state.config_data == mock_config_data

def test_init_load_config_not_exists():
    """Test initialization when config.json does not exist."""
    # Path.exists should return False for the config file
    with patch('utils.Path.exists', return_value=False) as mock_path_exists:
        state = YoutubeDataPipelineState(APP_DATA_DIR)
        
        # Ensure Path.exists was called for CONFIG_FILE_PATH
        mock_path_exists.assert_any_call(CONFIG_FILE_PATH)
        assert state.config_data == {}

def test_save_config():
    """Test saving the configuration."""
    m_open = mock_open()
    # Assume config.json doesn't initially exist for the __init__ call
    with patch('utils.Path.exists', return_value=False), \
         patch('builtins.open', m_open): # Patch open for the save_config call
        state = YoutubeDataPipelineState(APP_DATA_DIR)
        
        state.config_data = {"new_key": "new_value"}
        state.save_config() # This should call open(CONFIG_FILE_PATH, "w")
        
        m_open.assert_called_once_with(CONFIG_FILE_PATH, "w")
        m_open().write.assert_called_once_with(json.dumps({"new_key": "new_value"}))

# --- Test State Management Methods ---

@pytest.fixture
def state_with_mocked_save():
    """Provides a YoutubeDataPipelineState instance with save_config mocked and no initial config."""
    with patch('utils.Path.exists', return_value=False): # No config.json at init
        with patch.object(YoutubeDataPipelineState, 'save_config') as mock_save:
            state = YoutubeDataPipelineState(APP_DATA_DIR)
            state.save_config_mock = mock_save # Attach mock for easy access
            yield state # yield the state instance

def test_set_processing(state_with_mocked_save):
    state = state_with_mocked_save
    state.save_config_mock.reset_mock() # Reset from any init calls if applicable

    state.set_processing(True)
    assert state.config_data["processing"] is True
    state.save_config_mock.assert_called_once()

    state.set_processing(False)
    assert state.config_data["processing"] is False
    assert state.save_config_mock.call_count == 2

def test_is_processing(state_with_mocked_save):
    state = state_with_mocked_save
    state.config_data = {"processing": True}
    assert state.is_processing() is True

    state.config_data = {"processing": False}
    assert state.is_processing() is False

    state.config_data = {} 
    assert state.is_processing() is False

def test_set_keep_running(state_with_mocked_save):
    state = state_with_mocked_save
    state.save_config_mock.reset_mock()

    state.set_keep_running(True)
    assert state.config_data["keep_running"] is True
    state.save_config_mock.assert_called_once()

    state.set_keep_running(False)
    assert state.config_data["keep_running"] is False
    assert state.save_config_mock.call_count == 2

def test_is_keep_running(state_with_mocked_save):
    state = state_with_mocked_save
    state.config_data = {"keep_running": True}
    assert state.is_keep_running() is True

    state.config_data = {"keep_running": False}
    assert state.is_keep_running() is False

    state.config_data = {} 
    assert state.is_keep_running() is False

# --- Test File Existence Checks ---

WATCH_HISTORY_PATH = APP_DATA_DIR / "data/watch-history.html"
WATCH_HISTORY_ENRICHED_PATH = APP_DATA_DIR / "data/watch-history-enriched.csv"
WATCH_HISTORY_SUMMARY_PATH = APP_DATA_DIR / "data/watch-history-summary.json"
YOUTUBE_WRAPPED_PATH = APP_DATA_DIR / "data/youtube-wrapped.html"


# Mocking strategy for Path objects used by the state instance:
# We need to mock the Path *instances* that state.paths holds.
# The most reliable way is to mock the Path constructor utils.Path()
# to return specific mocks for specific path strings.

@pytest.fixture
def mock_path_instances(mocker): # mocker is a pytest fixture from pytest-mock
    """Mocks utils.Path constructor to return controllable Path instances."""
    path_mocks = {}

    def get_mock_path(path_str_or_obj):
        # Normalize to string to use as dict key
        path_key = str(path_str_or_obj)
        if path_key not in path_mocks:
            # Create a new MagicMock for this path if not already created
            # Use spec=Path to ensure it behaves like a Path object
            instance_mock = MagicMock(spec=Path, name=f"PathMock({path_key})")
            instance_mock.exists_result_to_return = False # Default exists to False
            instance_mock.exists.side_effect = lambda: instance_mock.exists_result_to_return
            
            # Mock resolve() to return itself or another mock if needed for chaining
            instance_mock.resolve.return_value = instance_mock 
            # Mock __str__ for when str() is called on the path mock
            instance_mock.__str__ = lambda self_obj: path_key 
            # Store the original path string/object for identification
            instance_mock._original_path_arg = path_str_or_obj

            # If path_str_or_obj is already a Path, copy relevant properties
            if isinstance(path_str_or_obj, Path):
                 instance_mock.name = Path(path_key).name # Make .name work
                 instance_mock.parent = Path(path_key).parent # Make .parent work
            
            path_mocks[path_key] = instance_mock
        return path_mocks[path_key]

    # Patch utils.Path constructor
    mock_constructor = mocker.patch('utils.Path', side_effect=get_mock_path)
    
    # Allow access to the created mocks and the constructor mock itself
    return {"mocks_map": path_mocks, "constructor": mock_constructor, "get_mock_path_func": get_mock_path}


@pytest.fixture
def state_with_mocked_paths(mock_path_instances):
    """Provides a state instance where all Path objects are mocks."""
    # Set config file to not exist by default for initialization
    config_path_mock = mock_path_instances["get_mock_path_func"](CONFIG_FILE_PATH)
    config_path_mock.exists_result_to_return = False
    
    state = YoutubeDataPipelineState(APP_DATA_DIR)
    state.path_mocks = mock_path_instances["mocks_map"] # Attach for easy access in tests
    return state

def test_source_data_exists_true(state_with_mocked_paths):
    state = state_with_mocked_paths
    state.path_mocks[str(WATCH_HISTORY_PATH)].exists_result_to_return = True
    assert state.source_data_exists() is True
    state.path_mocks[str(WATCH_HISTORY_PATH)].exists.assert_called_once()

def test_source_data_exists_false(state_with_mocked_paths):
    state = state_with_mocked_paths
    state.path_mocks[str(WATCH_HISTORY_PATH)].exists_result_to_return = False
    assert state.source_data_exists() is False
    state.path_mocks[str(WATCH_HISTORY_PATH)].exists.assert_called_once()

def test_enriched_data_exists_true(state_with_mocked_paths):
    state = state_with_mocked_paths
    state.path_mocks[str(WATCH_HISTORY_ENRICHED_PATH)].exists_result_to_return = True
    assert state.enriched_data_exists() is True
    state.path_mocks[str(WATCH_HISTORY_ENRICHED_PATH)].exists.assert_called_once()

def test_enriched_data_exists_false(state_with_mocked_paths):
    state = state_with_mocked_paths
    state.path_mocks[str(WATCH_HISTORY_ENRICHED_PATH)].exists_result_to_return = False
    assert state.enriched_data_exists() is False
    state.path_mocks[str(WATCH_HISTORY_ENRICHED_PATH)].exists.assert_called_once()

# --- Test Path Retrieval Methods ---
# These now use the mocked Path objects from state_with_mocked_paths

def test_get_enriched_data_path(state_with_mocked_paths):
    state = state_with_mocked_paths
    # The mock Path's __str__ and resolve() are set up in mock_path_instances
    # to return the original path string used for the key.
    expected_path_str = str(WATCH_HISTORY_ENRICHED_PATH.resolve()) # What the real code would produce
    assert state.get_enriched_data_path() == expected_path_str
    # Verify that resolve() was called on the specific path mock
    state.path_mocks[str(WATCH_HISTORY_ENRICHED_PATH)].resolve.assert_called_once()


def test_get_watch_history_path(state_with_mocked_paths):
    state = state_with_mocked_paths
    expected_path_str = str(WATCH_HISTORY_PATH.resolve())
    assert state.get_watch_history_path() == expected_path_str
    state.path_mocks[str(WATCH_HISTORY_PATH)].resolve.assert_called_once()


def test_get_watch_history_csv_path(state_with_mocked_paths):
    state = state_with_mocked_paths
    csv_path = APP_DATA_DIR / "data/watch-history.csv"
    expected_path_str = str(csv_path.resolve())
    assert state.get_watch_history_csv_path() == expected_path_str
    state.path_mocks[str(csv_path)].resolve.assert_called_once()


# --- Test File Size Calculation ---

def test_get_watch_history_file_size_mb_exists(state_with_mocked_paths):
    state = state_with_mocked_paths
    watch_history_mock = state.path_mocks[str(WATCH_HISTORY_PATH)]
    watch_history_mock.exists_result_to_return = True
    watch_history_mock.stat.return_value = MagicMock(st_size=2 * 1024 * 1024)  # 2 MB
    
    assert state.get_watch_history_file_size_mb() == 2.0
    watch_history_mock.exists.assert_called_once()
    watch_history_mock.stat.assert_called_once()

def test_get_watch_history_file_size_mb_not_exists(state_with_mocked_paths):
    state = state_with_mocked_paths
    watch_history_mock = state.path_mocks[str(WATCH_HISTORY_PATH)]
    watch_history_mock.exists_result_to_return = False
    
    assert state.get_watch_history_file_size_mb() == 0.0
    watch_history_mock.exists.assert_called_once()
    watch_history_mock.stat.assert_not_called() # stat() should not be called if file doesn't exist

# --- Test API Key Check ---
# This method re-reads config, so we need to mock 'open' and 'Path.exists' for CONFIG_FILE_PATH specifically.

def test_setup_api_key_exists_with_key(state_with_mocked_paths, mocker): # Use mocker from pytest-mock
    state = state_with_mocked_paths
    mock_config_data = {"youtube-api-key": "fake_key"}
    m_open = mock_open(read_data=json.dumps(mock_config_data))
    
    # Ensure that when state.config_path.exists() is called, it uses our mock
    config_path_mock = state.path_mocks[str(CONFIG_FILE_PATH)]
    config_path_mock.exists_result_to_return = True # Config file exists

    # Patch builtins.open for this test
    mocker.patch('builtins.open', m_open)
    
    assert state.setup_api_key() is True
    config_path_mock.exists.assert_called() # Called by setup_api_key
    m_open.assert_called_with(config_path_mock._original_path_arg, "r") # Check open called on original Path obj

def test_setup_api_key_exists_without_key(state_with_mocked_paths, mocker):
    state = state_with_mocked_paths
    mock_config_data = {"other_key": "other_value"}
    m_open = mock_open(read_data=json.dumps(mock_config_data))
    
    config_path_mock = state.path_mocks[str(CONFIG_FILE_PATH)]
    config_path_mock.exists_result_to_return = True

    mocker.patch('builtins.open', m_open)
    assert state.setup_api_key() is False

def test_setup_api_key_not_exists(state_with_mocked_paths):
    state = state_with_mocked_paths
    config_path_mock = state.path_mocks[str(CONFIG_FILE_PATH)]
    config_path_mock.exists_result_to_return = False # Config file does NOT exist
    
    assert state.setup_api_key() is False
    config_path_mock.exists.assert_called()


# --- Test DataFrame Dependent Methods ---
WATCH_HISTORY_CSV_RESOLVED_STR = str((APP_DATA_DIR / "data/watch-history.csv").resolve())
WATCH_HISTORY_ENRICHED_RESOLVED_STR = str((APP_DATA_DIR / "data/watch-history-enriched.csv").resolve())

# Fixture for state where relevant paths for DataFrame methods are mocked
@pytest.fixture
def state_for_df_tests(state_with_mocked_paths):
    # Ensure the Path mocks for CSV/Enriched files are accessible if needed,
    # though these methods use os.path.exists and string paths.
    # The key is that get_enriched_data_path() and get_watch_history_csv_path()
    # from the state object return the correct string paths.
    return state_with_mocked_paths


def test_get_enriched_rows_file_exists(state_for_df_tests, mocker):
    state = state_for_df_tests
    mock_df = pd.DataFrame({"duration_seconds": [10, None, 30, pd.NA, 50]})
    mocker.patch('utils.os.path.exists', return_value=True)
    mocker.patch('utils.pd.read_csv', return_value=mock_df)
    
    assert state.get_enriched_rows() == 3 
    utils.os.path.exists.assert_called_once_with(WATCH_HISTORY_ENRICHED_RESOLVED_STR)
    utils.pd.read_csv.assert_called_once_with(WATCH_HISTORY_ENRICHED_RESOLVED_STR)

def test_get_enriched_rows_file_not_exists(state_for_df_tests, mocker):
    state = state_for_df_tests
    mocker.patch('utils.os.path.exists', return_value=False)
    mocker.patch('utils.pd.read_csv') # Mock read_csv to ensure it's not called

    assert state.get_enriched_rows() == 0
    utils.os.path.exists.assert_called_once_with(WATCH_HISTORY_ENRICHED_RESOLVED_STR)
    utils.pd.read_csv.assert_not_called()


def test_get_processed_rows_file_exists(state_for_df_tests, mocker):
    state = state_for_df_tests
    mock_df = pd.DataFrame({"colA": [1, 2, 3, 4, 5]})
    mocker.patch('utils.os.path.exists', return_value=True)
    mocker.patch('utils.pd.read_csv', return_value=mock_df)

    assert state.get_processed_rows() == 5
    utils.os.path.exists.assert_called_once_with(WATCH_HISTORY_ENRICHED_RESOLVED_STR)
    utils.pd.read_csv.assert_called_once_with(WATCH_HISTORY_ENRICHED_RESOLVED_STR)


def test_get_years_file_exists(state_for_df_tests, mocker):
    state = state_for_df_tests
    mock_df = pd.DataFrame({
        "watch_time_dt": pd.to_datetime(["2020-01-01", "2021-05-10", "2020-03-15", None, "2022-11-20"])
    })
    mocker.patch('utils.os.path.exists', return_value=True)
    mocker.patch('utils.pd.read_csv', return_value=mock_df)
    
    assert state.get_years() == [2020, 2021, 2022]

def test_get_years_conversion_error(state_for_df_tests, mocker):
    state = state_for_df_tests
    # Simulate DataFrame where 'watch_time_dt' contains unparseable strings
    mock_df = pd.DataFrame({"watch_time_dt": ["invalid-date", "2020-01-01", "another-bad-one"]})
    mocker.patch('utils.os.path.exists', return_value=True)
    mocker.patch('utils.pd.read_csv', return_value=mock_df)
    mock_print = mocker.patch('utils.print') # To check if errors are logged as per implementation

    # errors='coerce' in pd.to_datetime will turn unparseable to NaT
    # The function should handle NaT values gracefully.
    assert state.get_years() == [2020] 
    # Verify if print was called for exceptions if any (depends on implementation's try-except)
    # Example: mock_print.assert_any_call(...)

def test_get_missing_rows_file_exists(state_for_df_tests, mocker):
    state = state_for_df_tests
    mock_df = pd.DataFrame({
        "error": ["some error", "not found video", "another error", "Video not found.", pd.NA, None, "all good"]
    })
    mocker.patch('utils.os.path.exists', return_value=True)
    mocker.patch('utils.pd.read_csv', return_value=mock_df)
    assert state.get_missing_rows() == 2

def test_get_total_rows_file_exists(state_for_df_tests, mocker):
    state = state_for_df_tests
    mock_df = pd.DataFrame({"colA": [1, 2, 3]})
    mocker.patch('utils.os.path.exists', return_value=True)
    mocker.patch('utils.pd.read_csv', return_value=mock_df)
    
    assert state.get_total_rows() == 3
    utils.os.path.exists.assert_called_once_with(WATCH_HISTORY_CSV_RESOLVED_STR)
    utils.pd.read_csv.assert_called_once_with(WATCH_HISTORY_CSV_RESOLVED_STR)


# --- Tests for step_3_summarize and step_4_publish ---

def test_step_3_summarize_exists(state_with_mocked_paths):
    state = state_with_mocked_paths
    state.path_mocks[str(WATCH_HISTORY_SUMMARY_PATH)].exists_result_to_return = True
    assert state.step_3_summarize() is True

def test_step_3_summarize_not_exists(state_with_mocked_paths):
    state = state_with_mocked_paths
    state.path_mocks[str(WATCH_HISTORY_SUMMARY_PATH)].exists_result_to_return = False
    assert state.step_3_summarize() is False

def test_step_4_publish_exists(state_with_mocked_paths):
    state = state_with_mocked_paths
    state.path_mocks[str(YOUTUBE_WRAPPED_PATH)].exists_result_to_return = True
    assert state.step_4_publish() is True

def test_step_4_publish_not_exists(state_with_mocked_paths):
    state = state_with_mocked_paths
    state.path_mocks[str(YOUTUBE_WRAPPED_PATH)].exists_result_to_return = False
    assert state.step_4_publish() is False

# --- Final check on paths definition ---
def test_paths_definition(state_with_mocked_paths):
    state = state_with_mocked_paths
    # Check that the paths stored in the state instance are our mocks
    # by comparing their _original_path_arg or by direct object comparison if stable
    assert state.paths["watch_history"]._original_path_arg == WATCH_HISTORY_PATH
    assert state.paths["watch_history_csv"]._original_path_arg == APP_DATA_DIR / "data/watch-history.csv"
    assert state.paths["watch_history_enriched"]._original_path_arg == WATCH_HISTORY_ENRICHED_PATH
    assert state.paths["watch_history_summary"]._original_path_arg == WATCH_HISTORY_SUMMARY_PATH
    assert state.paths["youtube_wrapped"]._original_path_arg == YOUTUBE_WRAPPED_PATH
    assert state.config_path._original_path_arg == CONFIG_FILE_PATH
