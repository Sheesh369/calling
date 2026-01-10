"""
Excel Service - Manage customer data and cutoff dates
"""
import os
import pandas as pd
from pathlib import Path
from datetime import datetime
from loguru import logger
from typing import Optional

# Directory to store customer data files
CUSTOMER_DATA_DIR = Path("customer_data")
CUSTOMER_DATA_DIR.mkdir(exist_ok=True)

# Default customer data file
CUSTOMER_DATA_FILE = CUSTOMER_DATA_DIR / "customer_data.xlsx"


def save_uploaded_file(uploaded_file_content: bytes, filename: str) -> str:
    """
    Save uploaded Excel/CSV file to persistent storage
    
    Args:
        uploaded_file_content: File content as bytes
        filename: Original filename
        
    Returns:
        Path to saved file
    """
    try:
        file_path = CUSTOMER_DATA_DIR / filename
        
        with open(file_path, "wb") as f:
            f.write(uploaded_file_content)
        
        logger.info(f"Saved customer data file: {file_path}")
        return str(file_path)
    
    except Exception as e:
        logger.error(f"Error saving uploaded file: {e}")
        raise


def load_customer_data(file_path: Optional[str] = None) -> pd.DataFrame:
    """
    Load customer data from Excel/CSV file
    
    Args:
        file_path: Path to customer data file (optional)
        
    Returns:
        DataFrame with customer data
    """
    try:
        if file_path is None:
            file_path = CUSTOMER_DATA_FILE
        
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.warning(f"Customer data file not found: {file_path}")
            return pd.DataFrame()
        
        # Load based on file extension
        if file_path.suffix == '.csv':
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        logger.info(f"Loaded customer data: {len(df)} records from {file_path}")
        return df
    
    except Exception as e:
        logger.error(f"Error loading customer data: {e}")
        return pd.DataFrame()


def update_cutoff_date(invoice_number: str, cutoff_date: str, commitment_text: str = None, 
                       file_path: Optional[str] = None) -> bool:
    """
    Update cutoff date for a specific invoice in the Excel file
    
    Args:
        invoice_number: Invoice number to update
        cutoff_date: Cutoff date in YYYY-MM-DD format
        commitment_text: The actual commitment text from transcript
        file_path: Path to customer data file (optional)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if file_path is None:
            file_path = CUSTOMER_DATA_FILE
        
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.warning(f"Customer data file not found: {file_path}")
            return False
        
        # Load existing data
        if file_path.suffix == '.csv':
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        # Add cutoff_date column if it doesn't exist
        if 'cutoff_date' not in df.columns:
            df['cutoff_date'] = None
            logger.info("Added 'cutoff_date' column to customer data")
        
        # Add commitment_text column if it doesn't exist
        if 'commitment_text' not in df.columns:
            df['commitment_text'] = None
            logger.info("Added 'commitment_text' column to customer data")
        
        # Find the row with matching invoice number
        mask = df['invoice_number'].astype(str) == str(invoice_number)
        
        if not mask.any():
            logger.warning(f"Invoice number {invoice_number} not found in customer data")
            return False
        
        # Update the cutoff date
        df.loc[mask, 'cutoff_date'] = cutoff_date
        
        # Update commitment text if provided
        if commitment_text:
            df.loc[mask, 'commitment_text'] = commitment_text
        
        # Save back to file
        if file_path.suffix == '.csv':
            df.to_csv(file_path, index=False)
        else:
            df.to_excel(file_path, index=False)
        
        logger.info(f"Updated cutoff date for invoice {invoice_number}: {cutoff_date}")
        return True
    
    except Exception as e:
        logger.error(f"Error updating cutoff date: {e}")
        return False


def get_customers_by_cutoff_date(cutoff_date: str, file_path: Optional[str] = None) -> pd.DataFrame:
    """
    Get all customers with a specific cutoff date
    
    Args:
        cutoff_date: Cutoff date in YYYY-MM-DD format
        file_path: Path to customer data file (optional)
        
    Returns:
        DataFrame with matching customers
    """
    try:
        df = load_customer_data(file_path)
        
        if df.empty or 'cutoff_date' not in df.columns:
            return pd.DataFrame()
        
        # Filter by cutoff date
        filtered_df = df[df['cutoff_date'] == cutoff_date]
        
        logger.info(f"Found {len(filtered_df)} customers with cutoff date {cutoff_date}")
        return filtered_df
    
    except Exception as e:
        logger.error(f"Error filtering by cutoff date: {e}")
        return pd.DataFrame()


def get_all_cutoff_dates(file_path: Optional[str] = None) -> list:
    """
    Get list of all unique cutoff dates in the customer data
    
    Args:
        file_path: Path to customer data file (optional)
        
    Returns:
        List of unique cutoff dates
    """
    try:
        df = load_customer_data(file_path)
        
        if df.empty or 'cutoff_date' not in df.columns:
            return []
        
        # Get unique cutoff dates, excluding None/NaN
        cutoff_dates = df['cutoff_date'].dropna().unique().tolist()
        cutoff_dates.sort()
        
        return cutoff_dates
    
    except Exception as e:
        logger.error(f"Error getting cutoff dates: {e}")
        return []
