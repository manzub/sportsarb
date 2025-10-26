import logging, os


def setup_logging(filename='arbitrage_finder.log'):
  base_dir = os.path.abspath(os.path.dirname(__file__))
  log_path = os.path.join(base_dir, '../static', filename)
  logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
  )
  return logging
