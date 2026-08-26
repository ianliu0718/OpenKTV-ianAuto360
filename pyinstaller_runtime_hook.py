import os
import sys

if getattr(sys, "frozen", False):
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
    internal_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    tensorflow_dir = os.path.join(internal_dir, "tensorflow", "python")
    os.environ["PATH"] = os.pathsep.join(
        [tensorflow_dir, internal_dir, os.environ.get("PATH", "")]
    )
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(internal_dir)
        if os.path.isdir(tensorflow_dir):
            os.add_dll_directory(tensorflow_dir)