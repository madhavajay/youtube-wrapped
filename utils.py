import json
import os
from pathlib import Path
import pandas as pd

class YoutubeDataPipelineState:
    def __init__(self, app_data_dir: Path):
        self.paths = {
            "watch_history": Path(app_data_dir / "data/watch-history.html"),
            "watch_history_csv": Path(app_data_dir / "data/watch-history.csv"),
            "watch_history_enriched": Path(app_data_dir / "data/watch-history-enriched.csv"),
            "watch_history_summary": Path(app_data_dir / "data/watch-history-summary.json"),
            "youtube_wrapped": Path(app_data_dir / "data/youtube-wrapped.html")
        }
        self.config_path = Path(app_data_dir / "cache" / "config.json")
        self.config_data = self.load_config()
        
    def load_config(self) -> dict:
        """Loads the configuration from the config.json file."""
        if self.config_path.exists():
            with self.config_path.open("r") as config_file:
                return json.load(config_file)
        return {}
        
    def save_config(self):
        """Saves the current configuration to the config.json file."""
        with self.config_path.open("w") as config_file:
            json.dump(self.config_data, config_file)
        
    def set_processing(self, processing: bool):
        """Sets the processing state and updates the config."""
        self.config_data["processing"] = processing
        self.save_config()
        
    def set_keep_running(self, keep_running: bool):
        """Sets the keep_running state and updates the config."""
        self.config_data["keep_running"] = keep_running
        self.save_config()

    def source_data_exists(self) -> bool:
        return self.paths["watch_history"].exists()

    def enriched_data_exists(self) -> bool:
        return self.paths["watch_history_enriched"].exists()
    
    def get_enriched_data_path(self) -> str:
        """Returns the absolute path to the watch-history-enriched.csv file."""
        return str(self.paths["watch_history_enriched"].resolve())

    def step_3_summarize(self) -> bool:
        return self.paths["watch_history_summary"].exists()

    def step_4_publish(self) -> bool:
        return self.paths["youtube_wrapped"].exists()

    def setup_api_key(self) -> bool:
        if self.config_path.exists():
            with self.config_path.open("r") as config_file:
                config_data = json.load(config_file)
                return "youtube-api-key" in config_data
        return False
    
    def get_watch_history_path(self) -> str:
        """Returns the absolute path to the watch-history.html file."""
        return str(self.paths["watch_history"].resolve())
    
    def get_watch_history_csv_path(self) -> str:
        """Returns the absolute path to the watch-history.csv file."""
        return str(self.paths["watch_history_csv"].resolve())
    
    def get_watch_history_file_size_mb(self) -> float:
        """Returns the file size of the watch-history.html file in megabytes."""
        if self.paths["watch_history"].exists():
            file_size_bytes = self.paths["watch_history"].stat().st_size
            file_size_mb = file_size_bytes / (1024 * 1024)  # Convert bytes to megabytes
            return file_size_mb
        return 0.0
    
    def is_processing(self) -> bool:
        """Returns True if processing is currently running, False otherwise."""
        return self.config_data.get("processing", False)
    
    def set_processing(self, processing: bool):
        """Sets the processing state."""
        self.config_data["processing"] = processing
        self.save_config()

    def is_keep_running(self) -> bool:
        """Returns True if keep_running is currently set, False otherwise."""
        return self.config_data.get("keep_running", False)
    
    def set_keep_running(self, keep_running: bool):
        """Sets the keep_running state."""
        self.config_data["keep_running"] = keep_running
        self.save_config()

    def get_enriched_rows(self) -> int:
        """Returns the number of processed rows with a valid duration."""
        enriched_data_path = self.get_enriched_data_path()
        if os.path.exists(enriched_data_path):
            df = pd.read_csv(enriched_data_path)
            return df['duration_seconds'].notna().sum()
        return 0
    
    def get_processed_rows(self) -> int:
        """Returns the number of processed rows with a valid duration."""
        enriched_data_path = self.get_enriched_data_path()
        if os.path.exists(enriched_data_path):
            df = pd.read_csv(enriched_data_path)
            return len(df)
        return 0
    
    def get_years(self) -> list:
        """Returns a sorted list of unique years from the 'watch_time_dt' column."""
        enriched_data_path = self.get_enriched_data_path()
        if os.path.exists(enriched_data_path):
            df = pd.read_csv(enriched_data_path)
            # Ensure 'watch_time_dt' is parsed as datetime
            df['watch_time_dt'] = pd.to_datetime(df['watch_time_dt'], errors='coerce')
            years = df['watch_time_dt'].dropna().dt.year.unique()
            return sorted(years.tolist())
        return []
    
    def get_missing_rows(self) -> int:
        """Returns the number of rows with errors indicating 'not found'."""
        enriched_data_path = self.get_enriched_data_path()
        if os.path.exists(enriched_data_path):
            df = pd.read_csv(enriched_data_path)
            filtered_df = df[df["error"].astype(str).str.contains("not found", case=False, na=False)]
            return len(filtered_df)
        return 0

    def get_total_rows(self) -> int:
        """Returns the total number of rows."""
        watch_history_csv_path = self.get_watch_history_csv_path()
        if os.path.exists(watch_history_csv_path):
            df = pd.read_csv(watch_history_csv_path)
            return len(df)
        return 0