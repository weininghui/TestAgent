from pathlib import Path
from typing import Dict, List
import json

from langchain_core.tools import tool

# Project root and output directories
PROJECT_ROOT = Path("E:/vs_test/AINew/aiagent-main")
OUTPUT_DIRS = [
    PROJECT_ROOT / "output",
    PROJECT_ROOT / "logs",
    PROJECT_ROOT / "data",
]


def _validate_path(path: str) -> Path:
    """Validate and resolve path to ensure it's within project boundaries.
    
    Args:
        path: The path to validate
        
    Returns:
        Path: Resolved absolute path
        
    Raises:
        ValueError: If path is outside project boundaries
    """
    # Convert to Path and resolve
    resolved_path = Path(path).resolve()
    
    # Check if path is within project root
    try:
        resolved_path.relative_to(PROJECT_ROOT)
    except ValueError:
        # Check if path is within any output directory
        is_output_dir = False
        for output_dir in OUTPUT_DIRS:
            try:
                resolved_path.relative_to(output_dir)
                is_output_dir = True
                break
            except ValueError:
                continue
        
        if not is_output_dir:
            raise ValueError(f"Path '{path}' is outside project boundaries")
    
    return resolved_path


@tool
def read_file(path: str) -> str:
    """Read any text file from the project.
    
    Args:
        path: Path to the file to read. Must be within project root or output directories.
        
    Returns:
        str: Content of the file as a string
        
    Raises:
        ValueError: If path is outside project boundaries
        FileNotFoundError: If file does not exist
        UnicodeDecodeError: If file cannot be decoded as UTF-8 (falls back to latin-1)
    """
    validated_path = _validate_path(path)
    
    if not validated_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    if not validated_path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    
    try:
        return validated_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Fallback to latin-1 if UTF-8 fails
        return validated_path.read_text(encoding="latin-1")


@tool
def list_directory(path: str) -> List[str]:
    """List files and directories at the given path.
    
    Args:
        path: Path to the directory to list. Must be within project root or output directories.
        
    Returns:
        List[str]: Sorted list of file and directory paths as strings
        
    Raises:
        ValueError: If path is outside project boundaries or is not a directory
    """
    validated_path = _validate_path(path)
    
    if not validated_path.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    
    if not validated_path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")
    
    # Get all entries and return sorted string paths
    entries = []
    for entry in validated_path.iterdir():
        entries.append(str(entry))
    
    return sorted(entries)


@tool
def file_exists(path: str) -> bool:
    """Check if a file exists at the given path.
    
    Args:
        path: Path to check. Must be within project root or output directories.
        
    Returns:
        bool: True if file exists, False otherwise
        
    Raises:
        ValueError: If path is outside project boundaries
    """
    try:
        validated_path = _validate_path(path)
        return validated_path.exists() and validated_path.is_file()
    except ValueError:
        return False


@tool
def read_json(path: str) -> Dict:
    """Read and parse a JSON file.
    
    Args:
        path: Path to the JSON file. Must be within project root or output directories.
        
    Returns:
        Dict: Parsed JSON data as a dictionary
        
    Raises:
        ValueError: If path is outside project boundaries
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file contains invalid JSON
    """
    validated_path = _validate_path(path)
    
    if not validated_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    if not validated_path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    
    try:
        with validated_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in file {path}: {e.msg}", e.doc, e.pos) from e


@tool
def write_json(path: str, data: Dict) -> None:
    """Write data to a JSON file.
    
    Args:
        path: Path to write the JSON file. Must be within project root or output directories.
        data: Dictionary data to write to the file
        
    Raises:
        ValueError: If path is outside project boundaries
        TypeError: If data is not JSON serializable
    """
    validated_path = _validate_path(path)
    
    # Ensure parent directory exists
    validated_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with validated_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise TypeError(f"Data is not JSON serializable: {e}") from e