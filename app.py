from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    get_flashed_messages,
)
from web3 import Web3
import requests
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("app_secret_key")

w3 = Web3(Web3.HTTPProvider(os.getenv("infura_api_key")))


def get_abi(address):
    response = requests.get(
        f"https://api.etherscan.io/api?module=contract&action=getabi&address={address}&apikey={os.getenv('etherscan_api_key')}"
    )
    return response.json()["result"]


def check_availability(args):
    mint = args[0]
    contract = args[1]
    method = getattr(contract.functions, "ownerOf")
    return method(mint).call()


def update_available_tokens(args):
    mint = args[0]
    contract = args[1]
    available_tokens = args[2]
    lock = args[3]
    try:
        check_availability([mint, contract])
        # print(f"Mint #{mint} is not available!")
    except:
        lock.acquire()
        available_tokens.append(mint)
        lock.release()
        # print(f"Mint #{mint} is available!")


@app.route("/")
def index():
    messages = get_flashed_messages(with_categories=True)
    if messages:
        message = json.loads(messages[0][1])
        error = message["error"]
        start = message["start"]
        stop = message["stop"]

        contract_address = message["contract_address"]
        return render_template(
            "index.html",
            error=error,
            start=start,
            stop=stop,
            contract_address=contract_address,
        )

    return render_template("index.html")


@app.route("/tokens", methods=["POST"])
def find_mints():
    start = int(request.form["start"])
    stop = int(request.form["stop"])
    contract_address = request.form["contract"]

    if stop < start:
        data = {
            "start": start,
            "stop": stop,
            "contract_address": contract_address,
            "error": "stop value has to be greater than start value",
        }
        flash(json.dumps(data))
        return redirect(url_for("index"))
    if stop - start > 500:
        data = {
            "start": start,
            "stop": stop,
            "contract_address": contract_address,
            "error": "stop value cannot be more than 500 greater than start value",
        }
        flash(json.dumps(data))
        return redirect(url_for("index"))

    time_start = time.time()

    abi = get_abi(contract_address)
    try:
        contract = w3.eth.contract(
            address=Web3.toChecksumAddress(contract_address), abi=abi
        )
    except:
        data = {
            "start": start,
            "stop": stop,
            "contract_address": contract_address,
            "error": "invalid contract address",
        }
        flash(json.dumps(data))
        return redirect(url_for("index"))

    lock = threading.Lock()
    available_tokens = []

    supply = stop - start

    with ThreadPoolExecutor(max_workers=300) as executor:
        executor.map(
            update_available_tokens,
            [[x, contract, available_tokens, lock] for x in range(start, stop)],
        )

    available_tokens.sort()

    time_end = time.time()

    time_string = f"<b>{len(available_tokens)}</b> items available, processed <b>{supply}</b> items in <b>{round(time_end - time_start, 3)}</b> seconds, average time of <b>{round((time_end - time_start) / supply, 3)}</b> seconds per item"

    return render_template(
        "tokens.html", time_string=time_string, tokens=available_tokens
    )


if __name__ == "__main__":
    app.run()
