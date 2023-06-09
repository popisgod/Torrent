# Standard library imports
import requests 
import socket 
import pickle 
import json
import os 
import hashlib
import pathlib
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
import shutil
import select
from threading import Thread
from time import sleep

# Third party imports 


# Local application imports
from utils import networking_utils 
from utils.setup import setup_peer

BUFSIZE = 3145728
TORRENT_FILES_DIR = '.torrent'
HOST_IP = ''
TRACKER_IP = ''

@dataclass
class Address:
    ip : str
    port : int

@dataclass
class Message: 
    msg : str
    data : Any

@dataclass
class FilePart:
    info_hash : str
    part_hash : str
    data : bytes | None = None
    part_num : int | None = None
    
    
class Peer: 
    def __init__(self) -> None:
        setup_peer()
        # tracker holding information about peers 
        self.tracker = f'http://{TRACKER_IP}:5000/'
        self.port = networking_utils.get_open_port()
        self.ip = HOST_IP
        self.peer_id = get_id()
        self.stopped = []
        self.peers = []
        
        os.makedirs(TORRENT_FILES_DIR, exist_ok=True)
        os.makedirs('downloads', exist_ok=True)

        # socket for connecting to peers 
        self.socket = socket.socket(
            socket.AF_INET, 
            socket.SOCK_STREAM
        )
        
        # server socket listening to peer requests 
        self.server = PeerServer(
            port=self.port,
            peer_id=self.peer_id
        )
        handle_connections_thread = Thread(
            target=self.server.handle_connections)
        handle_connections_thread.daemon = True
        handle_connections_thread.start()
        
        for torrent_name in os.listdir(TORRENT_FILES_DIR):
            with open(os.path.join(TORRENT_FILES_DIR, torrent_name), 'r') as file:
                data = json.load(file)
            self.announce(data['info_hash'], data['info']['name'], 'stopped')        


    def announce(self, info_hash : str, name : str, event : str) -> None | List[dict[str, str]]:
        
        try: 
            announce_url = self.tracker + 'announce/'

            
            params = {
                'name' : name, 
                'info_hash' : info_hash,
                'peer_id' : self.peer_id,
                'ip' : self.ip,
                'port' : self.port,
                'downloaded' : '0',
                'uploaded' : '0',
                'left' : '0',
                'event' : event
            } 
            
            announce_res = requests.get(announce_url, params=params, timeout=0.5)
            if announce_res.status_code != 200:
                print('api does not respond')

            for peer in announce_res.json():
                if peer not in self.peers:
                    self.peers.append(peer)
            
            return announce_res.json()
        except (requests.exceptions.ConnectionError, TimeoutError) as e:
            return self.peers 
               
        
    def create_torrent_file(self,file_path : str) -> str: 
        """

        Returns:
            str: file path of the torrent file 
        """
        chunk_size = BUFSIZE // 2
        path = pathlib.Path(file_path)
        os.makedirs(path.stem, exist_ok=True)

        

        parts = {}
        part_order = 0
        with open(file_path, 'rb') as file:
            file_hash = hashlib.sha256()
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                file_hash.update(chunk)

                chunk_hash = hashlib.sha256(chunk).hexdigest()
                chunk_file_path = os.path.join(path.stem, f"{chunk_hash}.bin")
                with open(chunk_file_path, 'wb') as chunk_file:
                    chunk_file.write(chunk)

                parts[part_order] = chunk_hash
                part_order += 1
            
        info = {
                'length' : os.path.getsize(file_path),
                'path' : '', 
                'name' : path.name,
                'piece length' : chunk_size,   
                'pieces' : parts,
                'file_hash' : file_hash.hexdigest(), 
                
            }
        info_hash = hashlib.sha256(bytes(json.dumps(info), 'utf-8')).hexdigest()
        torrent_dict = {
            'announce' : self.tracker,
            'info' : info, 
            'info_hash' : info_hash
            
        }
        
        if os.path.exists(info_hash): 
            shutil.rmtree(info_hash)
        os.rename(path.stem, info_hash)
        
        
        torrent_path = os.path.join(TORRENT_FILES_DIR, path.stem + '.torrent')
        with open(torrent_path, 'w') as file:
            json.dump(torrent_dict, file)
        
        return torrent_path
    
    
    def scrape(self) -> List[Dict[str,Any]]: 
        try: 
            url = self.tracker + 'scrape/all'
            res = requests.get(url, timeout=0.5)
            return res.json()
        except (requests.exceptions.ConnectionError, TimeoutError) as e:
            return [] 
            
    
    def get_torrent_file(self, info_hash : str, peers : List[Address]) -> Dict[str, Any] | None:
        # connect to peers 
        self.not_active = []
        for address in peers: 
            try: 
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((address.ip, address.port))
                self.socket.setblocking(True)
                
                msg = Message('$.torrent', info_hash)
                self.socket.send(pickle.dumps(msg))

                data = b""
                while True:
                    packet = self.socket.recv(BUFSIZE)
                    if not packet: break
                    data += packet
                recv_msg : Message = pickle.loads(data)
                
                if recv_msg.msg == '$.torrent': 
                    if recv_msg.data is not None:
                        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        return recv_msg.data
                


            except (socket.error, TimeoutError, Exception) as e: 
                print(f"Error connecting to {address.ip}:{address.port}: {e}")
                self.not_active.append(address)
        print('file wasn not found')
   

    def download_file(self, info_hash : str, name : str, pipe : int | None = None) -> None:
        peers = self.announce(info_hash, name, 'started')
        if peers is None:
            print('File does not exist')
            if pipe:
                os.write(pipe, json.dumps({'msg' : 'failed'}).encode())
            return

        addresss_list : List[Address] = []
        for peer in peers:
            addresss_list.append(Address(peer['ip'], int(peer['port'])))
            
        torrent_file = self.get_torrent_file(info_hash, addresss_list) 
        if torrent_file is None:
            print('File does not exist')
            if pipe:
                os.write(pipe, json.dumps({'msg' : 'failed'}).encode())
            return    
        
        for address in addresss_list:
            if address in self.not_active: 
                addresss_list.remove(address)
        
        with open(os.path.join(TORRENT_FILES_DIR, torrent_file['info']['name'].split('.')[0] + '.torrent'), 'w') as file:
            json.dump(torrent_file, file)
            
        
        os.makedirs(torrent_file['info_hash'],exist_ok=True)
        parts_missing = list(torrent_file['info']['pieces'].values())
        for part in os.listdir(torrent_file['info_hash']): 
            if part in parts_missing:
                parts_missing.remove(part)
        
        parts_per_peer = self.get_file_parts_availablity(info_hash, addresss_list)
        total = len(parts_missing)
        
        while parts_missing: 
            if pipe:
                os.write(pipe, json.dumps({'msg' : 'update', 'number' : 100 - int((len(parts_missing) / total) * 100)}).encode())
            if all(element == [] for element in list(parts_per_peer.values())):
                print('peers miss a part, file is not downloadable')
                if pipe:
                    os.write(pipe, json.dumps({'msg' : 'failed'}).encode())
                return 
          
            for address in addresss_list:
                parts_hash = parts_per_peer.get((address.ip, address.port), None)
                if parts_hash is not None:
                    try: 
                        for part_hash in parts_hash: 
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock: 
                                sock.connect((address.ip, address.port))
                                if part_hash in parts_missing:
                                    msg = Message('$part', FilePart(info_hash=info_hash, part_hash=part_hash))
                                    sock.send(pickle.dumps(msg))
                                    data = b""
                                    while True:
                                        packet = sock.recv(BUFSIZE)
                                        if not packet: break
                                        data += packet
                                        
                                    msg = pickle.loads(data).data 
                                    if part.data:
                                        if hashlib.sha256(part.data).hexdigest() == part_hash:
                                            with open(os.path.join(torrent_file['info_hash'], part_hash + '.bin'), 'wb') as file:
                                                file.write(part.data)
                                    
                                            parts_missing.remove(part_hash)    
                                    parts_hash.remove(part_hash)

                    except socket.error as e: 
                        print(f"Error connecting to {address.ip}:{address.port}: {e}")    
        
        with open(os.path.join('downloads', torrent_file['info']['name']),'wb') as file:
            for part_hash in torrent_file['info']['pieces'].values():
                with open(os.path.join(torrent_file['info_hash'], part_hash + '.bin'), 'rb') as part_file:
                    file.write(part_file.read())
        if pipe:
            os.write(pipe, json.dumps({'msg' : 'success'}).encode())
        
        self.announce(info_hash, name, 'completed')
        return {'status': 'success'}
        
        
    def get_file_parts_availablity(self, info_hash : str, peers : List[Address]) -> Dict[Tuple[str, int], List[str]]:
        
        parts_per_peer = {}
        for address in peers:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.connect((address.ip, address.port))
                    msg = Message('$parts_available', info_hash)
                    sock.send(pickle.dumps(msg))
                
                    data = b""
                    while True:
                        packet = sock.recv(BUFSIZE)
                        if not packet: break
                        data += packet
                    data = pickle.loads(data)
                parts_per_peer[(address.ip, address.port)] = data

            except socket.error as e: 
                print(f"Error connecting to {address.ip}:{address.port}: {e}")
        return parts_per_peer
        
            
    @staticmethod
    def torrent_file_exists(info_hash : str) -> Dict[str, Any] | None:
        for filename in os.listdir(TORRENT_FILES_DIR):
            # open file and read its contents 
            file_path = os.path.join(TORRENT_FILES_DIR, filename)
            with open(file_path, 'r') as file:
                data = json.load(file)
            
            if data['info_hash'] == info_hash:
                return data
        return None             


    @staticmethod
    def file_part_exists(file_part : FilePart) -> FilePart | None:
        part_path = os.path.join(file_part.info_hash, file_part.part_hash + '.bin')
        if os.path.exists(part_path):
            with open(part_path, 'rb') as file:
                file_part.data = file.read()
            return file_part
        return None


    @staticmethod
    def file_parts_available(info_hash : str) -> List[str]:
        hashes = []
        if os.path.exists(info_hash): 
            for filepart in os.listdir(info_hash):
                hash = filepart.split('.')[0]
                hashes.append(hash)
        return hashes


class PeerServer(socket.socket):
    def __init__(self, port : int, peer_id : str) -> None:
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.bind((HOST_IP, port))
        self.listen(5)
        self.setblocking
        self.peer_id = peer_id
        self.CONNECTION_LIST = [self,]
        
    def handle_connections(self) -> None:
        """
        
        
        """
        while True: 
            read_sockets, _, _ = select.select(
                self.CONNECTION_LIST,
                self.CONNECTION_LIST,
                self.CONNECTION_LIST
            )          
        
            for sock in read_sockets:
                if sock == self:
                    new_socket, _ = sock.accept()
                    self.CONNECTION_LIST.append(new_socket)
                    print(new_socket.getpeername(), 'has joined')
                else: 
                    try: 
                        msg = sock.recv(BUFSIZE)

                        if msg == b'':
                            self.disconnect(sock)
                        else: 
                            msg : Message = pickle.loads(msg) # type: ignore
                            print(msg)
                            
                            if msg.msg == "$.torrent": 
                                msg.data = Peer.torrent_file_exists(msg.data)
                                sock.send(pickle.dumps(msg))
                            
                            if msg.msg == "$parts_available":
                                msg.data = Peer.file_parts_available(msg.data)
                                sock.send(pickle.dumps(msg.data))
                            
                            if msg.msg == "$part": 
                                msg.data = Peer.file_part_exists(msg.data)
                                sock.send(pickle.dumps(msg))
                            self.disconnect(sock)
                    except socket.error as e:
                        self.disconnect(sock)    
                    except EOFError as e:
                        print(msg)
                            
                        
                            
    def disconnect(self, sock : socket.socket) -> None:
        if sock in self.CONNECTION_LIST:
            self.CONNECTION_LIST.remove(sock)
        print(sock.getpeername(), 'has disconnected')
        sock.close()


def get_id() -> str:
    with open('settings.json', 'r') as file:
        data = json.load(file)
    return data['UUID']
        
    
if __name__=='__main__':
    
    # ------- tests -------
    pass
