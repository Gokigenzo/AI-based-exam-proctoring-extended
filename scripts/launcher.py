import multiprocessing
import webbrowser
from threading import Timer
from examwatch.local.app import run

if __name__ == "__main__":
    multiprocessing.freeze_support()
    Timer(2, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    run()
