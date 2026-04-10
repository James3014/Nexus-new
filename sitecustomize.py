import warnings

# Suppress RequestsDependencyWarning at the earliest possible stage (Python startup)
# This works before pytest config loads and handles cases where plugins import requests early.
warnings.filterwarnings("ignore", message=".*RequestsDependencyWarning.*")
warnings.filterwarnings("ignore", message=".*doesn't match a supported version.*")
