import numpy as np
from unittest.mock import MagicMock, patch
from hbit.core import accelerator

def test_to_device_numpy():
    """Test to_device when using NumPy (CPU)."""
    # Force xp to be numpy
    with patch('hbit.core.accelerator.xp', np):
        test_array = np.array([1, 2, 3])
        result = accelerator.to_device(test_array)
        assert result is test_array

def test_to_device_cupy():
    """Test to_device when using CuPy (GPU)."""
    mock_cp = MagicMock()
    # Force xp to be cupy
    with patch('hbit.core.accelerator.xp', mock_cp):
        test_array = [1, 2, 3]
        mock_cp.asarray.return_value = "cupy_array"
        result = accelerator.to_device(test_array)
        mock_cp.asarray.assert_called_once_with(test_array)
        assert result == "cupy_array"

def test_to_cpu_numpy():
    """Test to_cpu when using NumPy (CPU)."""
    # Force xp to be numpy
    with patch('hbit.core.accelerator.xp', np):
        test_array = np.array([1, 2, 3])
        result = accelerator.to_cpu(test_array)
        assert result is test_array

def test_to_cpu_cupy_with_get():
    """Test to_cpu when using CuPy and array has .get() method."""
    mock_cp = MagicMock()
    with patch('hbit.core.accelerator.xp', mock_cp):
        mock_array = MagicMock()
        mock_array.get.return_value = np.array([1, 2, 3])
        result = accelerator.to_cpu(mock_array)
        mock_array.get.assert_called_once()
        assert isinstance(result, np.ndarray)

def test_to_cpu_cupy_without_get():
    """Test to_cpu when using CuPy but object doesn't have .get()."""
    mock_cp = MagicMock()
    # We need to patch np.asarray inside accelerator if we want to test that path
    with patch('hbit.core.accelerator.xp', mock_cp), \
         patch('hbit.core.accelerator.np.asarray') as mock_asarray:
        test_array = [1, 2, 3]
        mock_asarray.return_value = np.array([1, 2, 3])
        result = accelerator.to_cpu(test_array)
        mock_asarray.assert_called_once_with(test_array)
        assert isinstance(result, np.ndarray)
