# Heatwave Detection Dashboard

## Overview

The Heatwave Detection Dashboard is a desktop application designed for detecting, analyzing, and visualizing heatwave events using temperature data. Leveraging the capabilities of the `marineHeatWaves` library and a user-friendly interface built with `CustomTkinter`, this application allows users to upload temperature datasets, run heatwave detection, and generate insightful visualizations.

## Features

- **Data Upload**: Load temperature data from CSV files, including historical, current, and forecast data.
- **Detection Parameters**: Set climatology periods, percentiles, and duration for heatwave detection.
- **Event Detection**: Identify heatwave events for daytime, nighttime, and compound events.
- **Visualization Options**: Produce calendar plots, category plots, and timeseries plots to visualize data and detected events.
- **Preview Panel**: View detected heatwaves and statistics in a live preview panel.
- **Batch Processing**: Process multiple data stations in a batch run.
- **Logging and Robustness**: Features defensive coding with comprehensive logging for error tracking.

## Requirements

Before running the application, ensure you have the following installed:

- Python 3.x
- `CustomTkinter`
- `Pandas`
- `Numpy`
- `MarineHeatWaves`
- `Matplotlib`
- `Calplot` (Optional, for calendar heatmap visualization)
- `Pillow` (for image handling)

## Installation

1. Clone the repository or download the application files.
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate # On Windows use `venv\Scripts\activate`
   ```
3. Install the required dependencies:
   ```bash
   pip install customtkinter pandas numpy marineHeatWaves matplotlib calplot pillow
   ```
4. Run the application:
   ```bash
   python HW_Model_TK_v4.py
   ```

## User Manual

### 1. Opening Data
- Click on “Open CSV” to upload a temperature dataset in CSV format.

### 2. Configuring Detection Parameters
- Set options for the date, day temperature, night temperature, and station columns.
- Define climatology start and end years, percentile thresholds, minimum duration, and gap parameters.

### 3. Running Detection
- Select a station from the station dropdown menu.
- Click on “Run detection” to start identifying heatwave events. Results will populate the preview panel.

### 4. Visualizing Data
In the "More" tab, you can find:
- **Data Load**: Upload additional data and configure reference periods for further analyses.
- **Plotting**: Generate visualizations including calendar heatmaps and timeseries plots with options to save outputs.

### 5. Batch Processing
- In the "More" tab, use the "Batch run" function to upload a multi-station CSV file to process data for multiple stations simultaneously.

### 6. Saving Output
- Various options are provided to save plots and detected events as CSV or image files.

### 7. Logging and Diagnostics
- Log messages and application status updates are shown in the batch diagnostics area.

## Logging

All actions, including error messages and important events, are logged to `mhw_app.log` in the same directory as the application script. This log file can be reviewed for troubleshooting or application tracking.

## Acknowledgments

The application builds on the methodologies provided by the `marineHeatWaves` Python package for detecting and analyzing marine heatwave events. Developers and contributors of the `marineHeatWaves` library are acknowledged for their efforts.

## Developer

**Cosmos Senyo Wemegah** (PhD.)  
Research Fellow at EORIC-UENR, Ghana


## Support

For issues or questions regarding the application, please create an issue on the project's repository or contact the developer directly. 

--- 

This README provides a comprehensive guide for users, detailing installation steps, features, usage instructions, and acknowledgments. Adjustments can be made based on specific requirements or additions as needed.