cleanup() {
    echo "Terminating tendermint..."
    if kill -0 "$tm_subprocess_pid" 2>/dev/null; then
        kill "$tm_subprocess_pid"
        wait "$tm_subprocess_pid" 2>/dev/null
    fi
    echo "Tendermint terminated"
}

# Link cleanup to the exit signal
trap cleanup EXIT

# Remove previous agent if exists
if test -d learning_agent; then
  echo "Removing previous agent build"
  rm -r learning_agent
fi

# Remove empty directories to avoid wrong hashes
find . -empty -type d -delete

# Ensure hashes are updated
autonomy packages lock

# Fetch the agent
autonomy fetch --local --agent valory/learning_agent

# Replace params with env vars
source .env
python scripts/aea-config-replace.py

if [[ ! -f ethereum_private_key.txt ]]; then
    echo "ethereum_private_key.txt not found. Please provide or generate this file."
    exit 1
fi

# Copy and add the keys and issue certificates
cd learning_agent
cp $PWD/../ethereum_private_key.txt .
autonomy add-key ethereum ethereum_private_key.txt
autonomy issue-certificates

# Run tendermint
rm -r ~/.tendermint
tendermint init > /dev/null 2>&1
echo "Starting Tendermint..."
tendermint node --proxy_app=tcp://127.0.0.1:26658 --rpc.laddr=tcp://127.0.0.1:26657 --p2p.laddr=tcp://0.0.0.0:26656 --p2p.seeds= --consensus.create_empty_blocks=true > /dev/null 2>&1 &
tm_subprocess_pid=$!

# Run the agent
aea -s run
