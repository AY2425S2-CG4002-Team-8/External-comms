import paramiko
import threading
import socket
import sys
import time
import select
import config
import signal

stop_event = threading.Event()  # Global stop even

def reverse_tunnel(remote_port, local_host, local_port, transport):
    """
    Create an SSH reverse tunnel from the remote host to the local host.
    """
    try:
        transport.request_port_forward('', remote_port)
        print(f"Reverse SSH tunnel established: {remote_port} --> {local_host}:{local_port}")
    except Exception as e:
        print(f"Failed to establish reverse SSH tunnel: {e}")
        return

    while not stop_event.is_set():
        channel = transport.accept(1000)
        if channel is None:
            continue
        # Open a connection to the local host and port
        sock = socket.socket()
        try:
            sock.connect((local_host, local_port))
        except Exception as e:
            print(f"Forwarding request to {local_host}:{local_port} failed: {e}")
            channel.close()
            continue
        # Start a thread to forward data between the channels
        threading.Thread(target=handler, args=(channel, sock)).start()


def handler(channel, sock):
    while True:
        r, w, x = select.select([sock, channel], [], [])
        if sock in r:
            data = sock.recv(1024)
            if len(data) == 0:
                break
            channel.sendall(data)
        if channel in r:
            data = channel.recv(1024)
            if len(data) == 0:
                break
            sock.sendall(data)
    channel.close()
    sock.close()


def run_game_engine(client, remote_port):
    print(f"Running game server on Ultra96 using port {remote_port}...")

    try:
        print("Killing any existing relay server process on port 8080...")
        kill_command = 'sudo -E fuser -k 8080/tcp'
        kill_stdin, kill_stdout, kill_stderr = client.exec_command(kill_command, timeout=10)
        kill_stdin.write(f"{config.U96_PASSWORD}\n")
        kill_stdout.channel.recv_exit_status()  # Wait for the command to complete

        command = (
            'source /home/xilinx/capstone/External-comms/ge/bin/activate && '
            '. /etc/profile.d/xrt_setup.sh && '
            f'sudo -E python3 /home/xilinx/capstone/External-comms/main.py {remote_port}'
        )

        # Execute the remote command with PTY to handle sudo
        stdin, stdout, stderr = client.exec_command(command, get_pty=True)

        # Send the sudo password
        stdin.write(f"{config.U96_PASSWORD}\n")
        stdin.flush()

        # Start threads to read stdout and stderr
        threading.Thread(target=read_stream, args=(stdout, "STDOUT")).start()
        threading.Thread(target=read_stream, args=(stderr, "STDERR")).start()

    except Exception as e:
        print(f"Failed to run the game server on Ultra96: {e}")


def read_stream(stream, stream_name):
    for line in iter(lambda: stream.readline(2048), ""):
        if line:
            print(f"[REMOTE {stream_name}] {line}", end='')
        else:
            break


def main(local_port: int):
    local_host = '127.0.0.1'
    remote_port = config.U96_PORT
    remote_host = config.U96_HOST_NAME
    remote_user = config.U96_USER
    password = config.U96_PASSWORD

    try:
        # Create SSH client and connect
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(remote_host, username=remote_user, password=password)

        transport = client.get_transport()

        # Start reverse port forwarding in a separate thread
        reverse_tunnel_thread = threading.Thread(
            target=reverse_tunnel,
            args=(remote_port, local_host, local_port, transport),
            daemon=True
        )
        reverse_tunnel_thread.start()

        # Run the game server on the remote host
        run_game_engine(client, remote_port)

        def signal_handler(sig, frame):
            print("Shutting down...")
            stop_event.set()  # Signal threads to stop
            client.close()  # Close SSH connection
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Handle process termination

        # Keep the main thread alive to maintain the SSH connection
        while not stop_event.is_set():
            time.sleep(1)

    except KeyboardInterrupt:
        print("Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("No port number provided")
        sys.exit(1)

    local_port = int(sys.argv[1])
    main(local_port)