# Packages
import os
import pandas as pd

# Paths
"""Indicates which folder this script is saved in and navigates up one level into the data folder."""
DATA_DIR = os.path.join (os.path.dirname(__file__), "..", "data") 
"""Full path to the raw D17 RBA Excel file (this hasn't been edited to where data has been found from)."""
RAW_PATH = os.path.join (DATA_DIR, "F17_DATA_RAW.xlsx") 
"""Full path to the cache CSV."""
CACHE_PATH = os.path.join (DATA_DIR, "F17_DATA_CLEAN.csv")

# Maturities expressed in years (Title: Zero-Coupon Yield - Years)
"""Build the list of maturities with a range of 41 (0 to 40) and multiply by 0.25 to get the 0.25 year increments."""
maturities = [round (i * 0.25, 2) for i in range (41)] # Total of 41 maturities

# Starting row in Excel file for data.
""" The F17 Excel file has 11 rows of metadata that doesn't need to be read by pandas."""
data_start_row = 11

def load_raw() -> pd.DataFrame:
    """ Read the F17 Excel file with raw data and return a cleaned DataFrame."""
    df = pd.read_excel (RAW_PATH, sheet_name = 0, skiprows = data_start_row, header = None) # header = None says that none of the rows are treated as column names.

    """ Keep only the data column and (41) maturity columns for simplicity. """
    df = df.iloc[:, :42].copy() # Create a copy so that the original is not modified.
    """ Rename columns so that they express the date then the maturities."""
    df.columns = ["date"] + maturities

    # Parse Dates
    """Convert the date column from text/Excel format to datetime objects."""
    df ["date"] = pd.to_datetime (df["date"], errors = "coerce") # coerce turns any unparseable values into NaT (Not a Time) rather than crashing.
    df = df.dropna (subset = ["date"]) # Remove any rows where data couldn't be parsed (blank rows in Excel).

    # Convert rates from % per annum to decimals; treat zero/negative as missing.
    for mat in maturities:
        df [mat] = pd.to_numeric (df[mat], errors = "coerce") / 100 # divide by 100 to convert into deciaml form.
        df [mat] = df [mat].where (df [mat] > 0) 
    
    # Drop rows where all rate columns are missing.
    df = df.dropna (subset = maturities, how = "all") # Remove any rows where every single rate column in missing.
    df = df.sort_values ("date").reset_index (drop = True) # Sort by date to ensure chronological order, then reset index.

    return df

def sanity_check (df: pd.DataFrame) -> None:
    """ Run sanity checks on the cleaned data and print a summary.
        assert function raises an error immediately if the condition is false. It helps to identify if there is any bad data.
    """
    assert not df.empty, "DataFrame is empty after cleaning." # Ensure the DataFrame isn't empty after cleaning.
    assert df ["date"].is_monotonic_increasing, "Dates are not in ascending order" # Check dates are in ascending order which is a requirement for time series. 

    """Check each maturity column for implausible values."""
    for mat in maturities:
        col = df [mat].dropna() 
        assert (col > 0).all(), f"Non-positive rates found in {mat}year column." # Ensure that all interest rates are positive.
        assert (col < 0.30).all(), f"Implausibly high rates (>30&) in {mat}year column." # Ensure that there are no rates that are significantly high. If so, there might be an error with data.

    """Print a summary of the cleaned data to show readers."""
    latest = df.iloc [-1]
    print (f"[data_loader] Sanity checks passed.")
    print (f" Rows: {len(df)}")
    print (f" Data Range: {df['date'].iloc[0].date()} -> {df['date'].iloc[-1].date()}")
    print (f" Maturities: {len(maturities)} points (0 years to 10 years in 0.25 year increments)")
    print (f" Latest rates (% p.a.) - selected maturities:")
    for mat in [0, 0.25, 0.5, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]:
        """For readability, present in percentage format."""
        print (f" {mat:>5.2f}yr: {latest[mat]*100:.4f}%")

    """These functions are imported by other modules (yieldcurve.py, portfolio.py, etc.)"""

def load_yield_curve_data(use_cache: bool = True) -> pd.DataFrame:
    """
    Load cleaned F17 zero-coupon yield data.
    """

    """
    If the cached CSV file already exists, load from it instead of re-reading the Excel file for efficiency.
    """
    if use_cache and os.path.exists(CACHE_PATH):
        df = pd.read_csv(CACHE_PATH, parse_dates=["date"])
        df.columns = ["date"] + maturities # Reapply column names as CSV doesn't preserve our float column names.
        print(f"[data_loader] Loaded from cache: {CACHE_PATH}")
        return df
 
    """If the raw Excel file is missing, raise a clear error with instructions."""
    if not os.path.exists(RAW_PATH):
        raise FileNotFoundError(
            f"Raw data file not found at: {RAW_PATH}\n"
            "Download F17 from: https://www.rba.gov.au/statistics/tables/"
        )
 
    # Read and clean the raw Excel file.
    print(f"[data_loader] Reading raw file: {RAW_PATH}")
    df = load_raw()

    # Run sanity checks to confirm the data is valid before uisng.
    sanity_check(df)
 
    # Save the cleaned data to CSV so future runs skip the Excel processing step.
    df.to_csv(CACHE_PATH, index=False) # index = False prevents the pandas from writing the row numbers as an extra column.
    print(f"[data_loader] Cached cleaned data to: {CACHE_PATH}")
 
    return df
 
def get_latest_yields() -> tuple:
    """
    Return the most recent available zero-coupon rates.
 
    Returns
    date : str
        The date of the most recent observation (DD-MM-YYYY).
    yields : dict
        Mapping of maturity (float, years) -> zero rate (float, decimal).
        e.g. {0: 0.041, 0.25: 0.043, ..., 10.0: 0.050}
    """
    # Load from the cleaned data set.
    df = load_yield_curve_data()
    latest = df.iloc[-1] # iloc[-1] uses the most recent trading day in the dataset.
    date   = latest["date"].strftime("%d-%m-%Y") # Format the date into a readable string.
    yields = {mat: latest[mat] for mat in maturities} # Build a dictionary mapping each maturity to its zero-rate.
    return date, yields
 
if __name__ == "__main__":
    date, yields = get_latest_yields()
    print(f"\nLatest zero-coupon yields as of {date}:")
    for mat, rate in yields.items():
        if mat in [0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]:
            print(f"  {mat:>5.2f}yr : {rate*100:.4f}%")