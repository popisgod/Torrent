# Import necessary modules and functions
import socket
import pickle
import multiprocessing.pool
import select
import os
import shutil
from threading import Thread
import networking_utils
import torrent_utils

# --- Network Configuration ---


# Define host IP address, TCP port, and buffer size
HOST = ''
TORRENT_SERVER = '10.100.102.3'
TORRENT_PORT = 50142
HOST_IP = networking_utils.get_host_ip()
TCP_PORT = networking_utils.get_open_port()
BUFSIZ = 4096


class PeerToPeer(socket.socket):
    '''
    peer_to_peer server class
    '''
    @staticmethod
    def server() -> str:
        '''
        placeholder

        '''
        server = PeerToPeer()
        handle_connections_thread = Thread(
            target=server.handle_connections)
        handle_connections_thread.daemon = True
        handle_connections_thread.start()
        return server

    def __init__(self) -> None:
        '''
        intiate server socket and bind it.

        Args: 
            None.

        Returns:
            None.

        '''

        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        # Bind the server socket
        self.bind((HOST, TCP_PORT))
        self.listen(5)
        self.setblocking(0)
        self.CONNECTION_LIST = [self,]
        self.file_transfers = {}

    def handle_connections(self) -> None:
        '''
        Handles incoming connections from clients and creates sessions.

        Args:
            None.

        Returns:
            None.
        '''

        while True:

            # Get the list sockets which are ready to be read or write through select
            read_sockets, write_sockets, _ = select.select(
                self.CONNECTION_LIST, set(
                    self.CONNECTION_LIST).difference([self,]),
                self.CONNECTION_LIST)

            for sock in read_sockets:
                if sock == self:
                    new_socket, _ = sock.accept()
                    self.CONNECTION_LIST.append(new_socket)
                    print('new socket')
                    self.file_transfers[new_socket] = {
                        'file_name': None,
                        'file': None,
                        'remaining_size': 0
                    }
                else:

                    try:
                        res = sock.recv(BUFSIZ).decode()

                        # If file information is not yet received, interpret the received data as file info
                        if self.file_transfers[sock]['file_info']:
                            file = self.file_transfers[sock]['file']
                            remaining_size = self.file_transfers[sock]['remaining_size']
                            file.write(res)
                            self.file_transfers[sock]['remaining_size'] = remaining_size - len(
                                res)

                            # If the entire file is received, close the file and remove the client from the dictionary
                            if self.file_transfers[sock]['remaining_size'] == 0:
                                file.close()
                                print("File {} received".format(
                                    self.file_transfers[sock]['file_name']))
                                del self.file_transfers[sock]
                                self.CONNECTION_LIST.remove(sock)
                                sock.close()
                        else:
                            self.handle_client_commands(sock, res)

                    # In case of connection error, disconnect the client
                    except (ConnectionResetError, Exception) as e:
                        self.disconnect(sock)

    def handle_client_commands(self, client: socket.socket, command:  str) -> None:
        '''
        Process a command received from a client.

        Args:
            command (str): The command received from the client.
            sock (socket.socket): The client's socket connected to the server.

        Returns:
            str: A message to be sent back to the client.
        '''
        parts = command.split()
        msg_return = ''

        if parts[0] == '/upload_part':
            file_name, file_size = parts[1], parts[2]
            file_size = int(file_size)

            # Open the file for writing
            file_path = '/' + file_name
            self.file_transfers[client]['file_name'] = file_name
            self.file_transfers[client]['file'] = open(file_path, 'wb')
            self.file_transfers[client]['remaining_size'] = file_size

        elif parts[0] == '/download':
            pass
        elif parts[0] == '/disconnect':
            pass
        elif parts[0] == '/upload_complete':
            pass
        elif parts[0] == '/download_complete':
            pass

        client.send(msg_return)

    def disconnect(self, sock: socket.socket) -> None:
        '''
        Disconnects a client from the server, removes them from the active connection list.

        Args: 
            sock (socket):  socket of the client to be disconnected.

        Returns:
            None.
        '''

        self.CONNECTION_LIST.remove(sock)
        sock.close()


class TorrentClient(socket.socket):
    '''
    Torrent client class 
    '''
    @staticmethod
    def server() -> str:
        '''
        placeholder
        '''
        server = TorrentClient()
        receive_thread = Thread(
            target=server.receive_wrapper)
        receive_thread.daemon = True
        receive_thread.start()
        return server

    def __init__(self) -> None:
        '''
        intiate client socket and connect it to the server.

        Args: 
            None.

        Returns:
            None.

        '''

        super().__init__(socket.AF_INET, socket.SOCK_STREAM)

        # connect to the server socket
        self.connect((TORRENT_SERVER, TORRENT_PORT))
        self.actions = []

    def receive_wrapper(self) -> None:
        '''
        placeholder
        '''

        while True:
            try:
                res = self.recv(BUFSIZ)
                res_loaded = pickle.loads(res)

                if res_loaded[0] == '/port':
                    msg_return = ' '.join(('!port', TCP_PORT))
                    self.send(msg_return.encode())

                if res_loaded[0] in self.actions:
                    self.actions.remove(res_loaded[0])
                    print(res_loaded[0])
                    self.execute_command(res_loaded[0], res_loaded[1])

            # In case of connection error, disconnect the client
            except (ConnectionResetError, Exception) as e:
                pass

    def send_command(self, command: str) -> None:
        '''
        placeholder

        '''
        self.actions.append(command)
        self.send(command.encode())

    def update_torrent_server(self, update: str) -> None:
        '''
        placeholder
        '''
        self.send(update.encode())

    def execute_command(self, command: str, other) -> None:
        '''
        Process a command received from the client.

        '''
        parts = command.split(' ')
        msg_return = ''

        if parts[0] == '/upload':
            self.upload_file_to_network(other, parts[1])

        elif parts[0] == '/downlod':
            pass
        elif parts[0] == '/disconnect':
            pass
        elif parts[0] == '/upload_complete':
            pass
        elif parts[0] == '/download_complete':
            pass

    def upload_file_to_network(self, peers_info: tuple((list[(str, int)],
                                                       dict)), file_path: str) -> None:
        '''
        divides the file and uploads it to the peers that are in the provided list. 
        updates the torrent server about the upload.

        Args: 
            peers list[(str,int)]: ip and port pairs of the peers sockets 
            file_path (str): file path 

        Returns: 
            None.
        '''

        # get the file name from the file path
        file_name = file_path.split('/')[-1].split('.')[0]

        peers = peers_info[0]
        file_parts_paths = torrent_utils.package_computer_parts(
            file_name, file_path, len(peers), len(peers)//2)
        print('hello')
        
        # create socket connection with peers
        socket_peers = []
        for peer in peers:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect(peer)
                socket_peers.append(s)
            except ConnectionRefusedError:
                continue

        # create processesing pool and start sending the files
        with multiprocessing.pool.ThreadPool(processes=len(peers)) as pool:
            for file_status in pool.starmap(send_file, (file_parts_paths, socket_peers)):
                if file_status[0]:
                    peer_ip = file_status[2].gethostbyname(
                        file_status[2].gethostname())
                    self.update_torrent_server(
                        ' '.join(('/update', file_status[1], (peers_info[1][peer_ip]))))
                else:
                    pass

        # close the peer sockets
        for peer in socket_peers:
            peer.close()

        # delete the temp dir storing the tar files
        shutil.rmtree(os.path.dirname(file_parts_paths[0]))


def send_file(file_parts_paths: str, peer: socket.socket) -> list[bool, str, socket.socket]:
    '''


    Returns:
        list[bool,str, socket.socket]:True if upload was successful false otherwise,  
                                        metadata of the file uploaded, and socket

    '''
    try:
        # get the file name and size to send the server
        file_path = file_parts_paths[0]
        file_name = file_path.split('/')[-1].split('.')[0]
        file_size = os.path.getsize(file_path)
        peer.send(f"/upload_part {file_name} {file_size}".encode())

        # Open the file for reading
        with open(file_path, 'rb') as file:
            # Send file chunks until the entire file is sent
            while True:
                chunk = file.read(BUFSIZ)
                if not chunk:
                    break
                peer.send(chunk)
    except (ConnectionResetError, Exception) as e:
        return [False, file_parts_paths[1], peer]
    return [True, file_parts_paths[1], peer]


if __name__ == '__main__':
    torrent_client = TorrentClient.server()
    peer_to_peer = PeerToPeer.server()

    while True:
        torrent_client.send_command(input().strip())
