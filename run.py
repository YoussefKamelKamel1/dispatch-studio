"""Run Dispatch and its local publishing APIs on one loopback server."""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
import uvicorn

root = Path(__file__).resolve().parent
load_dotenv(root / '.env')
parser = argparse.ArgumentParser(description='Dispatch local application server')
parser.add_argument('--port', type=int, default=int(os.getenv('DISPATCH_PORT', '8012')))
parser.add_argument('--data-dir', help='Optional separate data directory for demonstrations or tests')
parser.add_argument('--base-url', help='URL the publishing worker uses to reach this local server')
args = parser.parse_args()
if args.data_dir:
    os.environ['DATA_DIR'] = str(Path(args.data_dir).resolve())
os.environ['DISPATCH_BASE_URL'] = args.base_url or f'http://127.0.0.1:{args.port}'
os.chdir(root)
uvicorn.run('backend.app:app', host='127.0.0.1', port=args.port)
