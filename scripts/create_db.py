import sys
import os

# Ensure project root is on sys.path so local modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import init_database, add_test_data, DB_PATH


if __name__ == '__main__':
    init_database()
    add_test_data()
    print('DB_CREATED_AT:', DB_PATH)
