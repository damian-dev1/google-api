# try_connect_sftp_with_retries
import paramiko
import os
from dotenv import load_dotenv
from pathlib import Path
import time
from datetime import datetime, timezone
from pathlib import Path
import logging
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import socket

load_dotenv()

SFTP_HOST = os.getenv("SFTP_HOST")
SFTP_PORT = int(os.getenv("SFTP_PORT", "22"))  # cast to int
# SFTP_USERNAME = os.getenv("SFTP_USERNAME")
# SFTP_PASSWORD = os.getenv("SFTP_PASSWORD")
UAT_SFTP_USERNAME = os.getenv("UAT_SFTP_USERNAME")
UAT_SFTP_PASSWORD = os.getenv("UAT_SFTP_PASSWORD")
REMOTE_DIR = os.getenv("REMOTE_DIR")
LOCAL_DIR = Path(os.getenv("LOCAL_DIR"))
INCREMENTAL_PREFIX = os.getenv("INCREMENTAL_PREFIX")
FULL_INVENTORY_PREFIX = os.getenv("FULL_INVENTORY_PREFIX")
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds
LOCAL_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = "sqlite:///logging.db"

# Set up the SQLAlchemy engine and session
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# Define the base class for declarative models
Base = declarative_base()

# Define the LogEntry model
class LogEntry(Base):
    __tablename__ = 'log_entries'
    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String, nullable=False)
    message = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))

# Create the log_entries table
Base.metadata.create_all(engine)

# Define a custom logging handler
class SQLAlchemyHandler(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)

    def emit(self, record):
        log_entry = LogEntry(
            level=record.levelname,
            message=record.getMessage(),
            timestamp=datetime.utcnow()
        )
        session.add(log_entry)
        session.commit()

# Set up the logger
logger = logging.getLogger('sqlalchemy_logger')
logger.setLevel(logging.DEBUG)
sqlalchemy_handler = SQLAlchemyHandler()
logger.addHandler(sqlalchemy_handler)

def connect_sftp():
    """Establish a secure SFTP connection with timeouts."""
    try:
        sock = socket.create_connection((SFTP_HOST, SFTP_PORT), timeout=10)
        transport = paramiko.Transport(sock)
        transport.start_client(timeout=10)
        transport.auth_password(UAT_SFTP_USERNAME, UAT_SFTP_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)
        return sftp
    except (paramiko.SSHException, socket.timeout, socket.error) as e:
        logger.error(f"Failed to connect to SFTP: {e}")
        raise

def get_latest_file(sftp, prefix):
    """Retrieve the latest file from SFTP matching a given prefix."""
    try:
        files = [f for f in sftp.listdir(REMOTE_DIR) if f.startswith(prefix)]
        if not files:
            return None
        files.sort(reverse=True)  # Sort by timestamp (latest first)
        return files[0]
    except Exception as e:
        logger.error(f"Error retrieving latest file: {e}")
        return None

def download_file(sftp, filename):
    """Download a file from SFTP to local storage."""
    remote_path = f"{REMOTE_DIR}/{filename}"
    local_path = LOCAL_DIR / filename
    try:
        sftp.get(remote_path, str(local_path))
        logger.info(f"Downloaded: {filename}")
        return local_path
    except Exception as e:
        logger.error(f"Error downloading {filename}: {e}")
        return None

def process_inventory_file(file_path):
    """Process the inventory file (placeholder for actual processing logic)."""
    logger.info(f"Processing file: {file_path}")
    # TODO: Implement actual inventory processing logic here
    time.sleep(2)  # Simulating processing time


def main():
    last_processed_incremental = None
    last_processed_full = None

    while True:
        current_time = datetime.now()
        minutes = current_time.minute
        sftp = None  # Ensure sftp is defined

        try:
            sftp = try_connect_sftp_with_retries()

            if minutes >= 50:
                latest_full_file = get_latest_file(sftp, FULL_INVENTORY_PREFIX)
                if latest_full_file and latest_full_file != last_processed_full:
                    local_file = download_file(sftp, latest_full_file)
                    if local_file:
                        process_inventory_file(local_file)
                        last_processed_full = latest_full_file
                        last_processed_incremental = None
            else:
                latest_incremental_file = get_latest_file(sftp, INCREMENTAL_PREFIX)
                if latest_incremental_file and latest_incremental_file != last_processed_incremental:
                    local_file = download_file(sftp, latest_incremental_file)
                    if local_file:
                        process_inventory_file(local_file)
                        last_processed_incremental = latest_incremental_file

        except (paramiko.SSHException, socket.timeout, ConnectionResetError) as e:
            logger.error(f"Connection-related error: {e}")
            logger.info("Attempting disaster recovery...")

            try:
                sftp = try_connect_sftp_with_retries()
                latest_full_file = get_latest_file(sftp, FULL_INVENTORY_PREFIX)
                if latest_full_file and latest_full_file != last_processed_full:
                    local_file = download_file(sftp, latest_full_file)
                    if local_file:
                        process_inventory_file(local_file)
                        last_processed_full = latest_full_file
                        last_processed_incremental = None
            except Exception as recovery_error:
                logger.error(f"Disaster recovery failed: {recovery_error}")

        except Exception as general_error:
            logger.error(f"Unexpected error: {general_error}")

        finally:
            if sftp:
                try:
                    sftp.close()
                except Exception as close_error:
                    logger.warning(f"Failed to close SFTP session cleanly: {close_error}")

        time.sleep(300)


def try_connect_sftp_with_retries():
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return connect_sftp()
        except Exception as e:
            logger.warning(f"SFTP connection attempt {attempt} failed: {e}")
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_DELAY * attempt)


if __name__ == "__main__":
    main()
