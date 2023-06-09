# Standard library imports
from ast import Not
from email.errors import FirstHeaderLineIsContinuationDefect
import json
from typing import Dict, List, Any, Tuple
from threading import Thread
from time import sleep
import json
import tkinter as tk
from tkinter import font
from tkinter import ttk
from tkinter import filedialog
import time 
import os 


# Third party imports 
from PIL import Image, ImageTk, ImageOps
import requests

# Local application imports
import peer

FIRST = True
REFRESH_INTERVAL = 5
# Set Discord-inspired colors
DISCORD_DARK_BLUE = "#2C2F33"
DISCORD_GRAY = "#2f3136"
DISCORD_BLUE = "#7289DA"
DISCORD_LIGHT_GRAY = "#36393f"
DISCORD_WHITE = "#FFFFFF"
BACKGROUND_COLOR = "#313338"
PRIMARY_COLOR = "#5865F2"
SECONDARY_COLOR = "#99AAB5"
TEXT_COLOR = "#B5BAC1"
ENTRY_COLOR = "#1E1F22"


class PeerGUI(tk.Tk): 
    def __init__(self) -> None:
        super().__init__()
        self.peer : peer.Peer = peer.Peer()
        self.create_session_list_window()

    def create_session_list_window(self):
        """
        Create a tkinter window to display a list of sessions.

        Args:
            root (tk.Tk): The window of the chat room application.
            client (socket.socket): A client socket connected to the server.

        Returns:
            tk.Toplevel: a tkinter window of the list of sessions
        """
        self.title("Torrent List")
        self.configure(bg="#1e1e1e")

        # Set the window size and position
        window_width = 1400
        window_height = 340
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = int((screen_width / 2) - (window_width / 2)) - 100
        y = int((screen_height / 2) - (window_height / 2))
        self.geometry("{}x{}+{}+{}".format(window_width, window_height, x, y))
        self.minsize(300, 335)
        self.maxsize(None, 1000)

        # Create a style for the window and widgets
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background='#1e1e1e',
                        foreground='white', font=('Helvetica', 10))
        style.configure('TButton', padding=6, relief='flat',
                        background='#424242', foreground='white', font=('Helvetica', 10))
        style.configure('TLabel', padding=6, background='#1e1e1e', foreground='white', font=('Helvetica', 10))
        style.configure('TEntry', padding=6, relief='flat', background='#424242', foreground='white', font=('Helvetica', 10))
        style.map('TButton', background=[
                ('active', '#606060')], foreground=[('active', 'white')])

        # Create a frame for the listbox and scrollbar
        frame = ttk.Frame(self)
        frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Create a listbox to display the sessions
        listbox = tk.Listbox(frame, bg='#2b2b2b', fg='white', font=('Helvetica', 11),
                            selectmode='browse', highlightthickness=0, activestyle="none",
                            takefocus=False, selectbackground='#3f3f3f', selectforeground='white')
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        listbox.bind("<Double-Button-1>", lambda event: self.create_download_window(event))
        self.reload_sessions(listbox)
        self.listbox = listbox

        # Create a scrollbar for the listbox
        scrollbar = tk.Scrollbar(frame, bg='#1e1e1e', activebackground='#1e1e1e',
                                troughcolor='#2b2b2b', command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)

        # Create a frame for the buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)

        # Create a Reload button to reload the session list
        reload_button = ttk.Button(button_frame, text="Reload",
                                command=lambda: self.reload_sessions(listbox))
        reload_button.pack(side=tk.LEFT, anchor=tk.W, padx=5)

        # Create a Create Session button to create a new session
        create_torrent = ttk.Button(
            button_frame, text="Create torrent", command=self.create_torrent_window)
        create_torrent.pack(side=tk.LEFT, padx=5, anchor=tk.W)
        self.create_torrent = create_torrent

        
        image_file = "question_mark.png"
        image = Image.open(image_file)
        image = image.resize((15, 15))
        question_mark_photo = ImageTk.PhotoImage(image)
    
        # Create a help button to open a help screen 
        help_button = ttk.Button(
            button_frame, image=question_mark_photo,command=lambda: self.create_help_window())
        help_button.image = question_mark_photo
        help_button.pack(side=tk.LEFT, anchor=tk.W, padx=5)

        self.server_status = ttk.Label(
            button_frame, text="server is UP", foreground='green')
        self.server_status.pack(side=tk.LEFT, padx=5, anchor=tk.W)


        thread = Thread(target=self.wrapper)
        thread.daemon = True
        thread.start()

    def update_lists(self):
        try: 
            self.reload_sessions(self.listbox)
            self.create_torrent.config(state='normal')
            self.server_status.config(text='server is UP',foreground='green')
        except (requests.exceptions.ConnectionError, TimeoutError) as e:
            print('server is downs')
            self.server_status.config(text='server is DOWN',foreground='red')
            self.create_torrent.config(state='disabled')
            time.sleep(REFRESH_INTERVAL)
            
    def wrapper(self):
        while True: 
            self.update_lists()
            time.sleep(REFRESH_INTERVAL)

    def reload_sessions(self, listbox) -> None:
        """
        Reloads the sessions list from the server and updates the session listbox.

        Args:
            client (socket.socket): The client socket connected to the server.
            listbox (tk.Listbox): The tkinter listbox that holds the sessions. 

        Returns:
            None.
        """

        data = self.peer.scrape()        

        if len(data) == listbox.size():
            return

        listbox.selection_clear(0, tk.END)
        listbox.delete(0, tk.END)
        list_file_names = []

        for torrent_file in os.listdir('.torrent'):
            with open(os.path.join('.torrent',torrent_file), 'r') as file:
                torrent_data = json.load(file)
            self.peer.announce(torrent_data['info_hash'], torrent_data['info']['name'], 'completed')
            list_file_names.append(torrent_data['info']['name'])
            if len(data) == 0: 
                if listbox.size() == 0:
                    if torrent_data['info']['name'] in os.listdir('downloads'):
                        listbox.insert(tk.END, f"{torrent_data['info']['name']} -| {torrent_data['info_hash']} -| downloaded") 
                    else: 
                       listbox.insert(tk.END, f"{torrent_data['info']['name']} -| {torrent_data['info_hash']}") 
                    listbox.selection_set(tk.END, None)
        if len(data) == 0:
            raise TimeoutError

        # iterate over the sessions list received from the server and add them to the listbox
        for i, file in enumerate(data):
            if file['name'] in os.listdir('downloads'):
                listbox.insert(tk.END, f"{file['name']} -| {file['info_hash']} -| peers : {len(file['peers'])} -| downloaded") 
            else: 
                listbox.insert(tk.END, f"{file['name']} -| {file['info_hash']} -| peers : {len(file['peers'])}") 
            listbox.selection_set(tk.END, None)


    def create_help_window(self) -> None: 
        """
        Creates a new window for user help.
        
        Args:
            None.
            
        Returns: 
            None.
        """
        # Create a new window for the login
        help_window = tk.Toplevel(self)
        #help_window.resizable(False, False)
        help_window.grab_set()
        help_window.focus_set()

        # Set the title of the window to be "login"
        help_window.title("help")
        help_window.configure(bg="#1e1e1e")

        # Set the window size and position
        window_width = 700
        window_height = 200
        screen_width = help_window.winfo_screenwidth()
        screen_height = help_window.winfo_screenheight()
        x = int((screen_width/2) - (window_width/2))
        y = int((screen_height/2) - (window_height/2))
        help_window.geometry("{}x{}+{}+{}".format(window_width, window_height, x, y))
        help_window.resizable(False,False)
        
        # Create a style for the window and widgets
        style = ttk.Style(help_window)
        style.theme_use('clam')
        style.configure('.', background='#1e1e1e', foreground='white', font=('Helvetica', 10))
        style.configure('TLabel', padding=6, background='#1e1e1e', foreground='white', font=('Helvetica', 10))
        style.configure('TEntry', padding=6, relief='flat', background='#424242', foreground='white', font=('Helvetica', 10))
        style.configure('TButton', padding=6, relief='flat', background='#424242', foreground='white', font=('Helvetica', 10))
        style.map('TButton', background=[('active', '#606060')], foreground=[('active', 'white')])

        # Create a frame for the login form
        form_frame = ttk.Frame(help_window)
        form_frame.pack(fill='both', expand=True, padx=10, pady=10)

        help_text = '''
        welcome to my torrent client!
        
        infront of you is a list of the available torrent files.
        you can try to download them all, some might be inactive so you won't be able to download them sadly.
        you can also create a torrent file by selecting create torrent file and selecting a file with the file explorer. 
        this file will be uploaded to the tracker server and now other people will be able to see it.
        
        
        '''
        
        # Create a label for the password field
        help_label = ttk.Label(form_frame, text=help_text)
        help_label.grid(row=0, column=0, sticky='w')


    def create_download_window(self, event : tk.Event) -> None:
        """
        This function is called when the user selects a session from the list of available sessions. 
        It creates a new window for the user to enter their login information, and launches the login process when the 
        user clicks the login button.

        Args:
            event (tk.Event): The event that triggered the function call (the user selecting a session from the list).
        
        Returns:
            None.
        """
        # Get the session ID and name using regex
        selected_index = event.widget.curselection()[0]
        selected_item = event.widget.get(selected_index).strip().split('-|')
        name = selected_item[0].strip()
        info_hash = selected_item[1].strip()


        # Create a new window for the login
        login_window = tk.Toplevel(self)
        login_window.resizable(False, False)
        login_window.grab_set()
        login_window.focus_set()

        # Set the title of the window to be "login"
        login_window.title("download")
        login_window.configure(bg="#1e1e1e")

        # Set the window size and position
        window_width = 300
        window_height = 170 
        screen_width = login_window.winfo_screenwidth()
        screen_height = login_window.winfo_screenheight()
        x = int((screen_width/2) - (window_width/2))
        y = int((screen_height/2) - (window_height/2))
        login_window.geometry(
            "{}x{}+{}+{}".format(window_width, window_height, x, y))

        # Create a style for the window and widgets
        style = ttk.Style(login_window)
        style.theme_use('clam')
        style.configure('.', background='#1e1e1e',
                        foreground='white', font=('Helvetica', 10))
        style.configure('TLabel', padding=6, background='#1e1e1e',
                        foreground='white', font=('Helvetica', 10))
        style.configure('TEntry', padding=6, relief='flat',
                        background='#424242', foreground='white', font=('Helvetica', 10))
        style.configure('TButton', padding=6, relief='flat',
                        background='#424242', foreground='white', font=('Helvetica', 10))
        style.map('TButton', background=[
                ('active', '#606060')], foreground=[('active', 'white')])

        # Create a frame for the login form
        form_frame = ttk.Frame(login_window)
        form_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Create a label for the download status
        status_label = ttk.Label(form_frame, text="Click to download", foreground="white")
        status_label.pack(pady=10)

        progress = ttk.Progressbar(form_frame, mode='determinate', maximum=100,length=200)
        progress.pack(pady=10)

        # Create a function to simulate the download progress
        def download_bar(info_hash : str, name : str):
 
            submit_button.configure(state='disabled')  # Disable the download button
            status_label.config(text="Downloading...")
                  # Start the progress bar
            read_pipe, write_pipe = os.pipe()
            
            download_thread = Thread(target=self.download, args=(info_hash, name, write_pipe))
            download_thread.daemon = True
            download_thread.start()
            
            progress_bar_handler = Thread(target=handle_progress_bar, args=(write_pipe, read_pipe))
            progress_bar_handler.daemon = True
            progress_bar_handler.start()        
            
        def handle_progress_bar(write_pipe, read_pipe): 
            
           # Simulate the download progress
            while True: 
                data = os.read(read_pipe, 1024) # Simulate some delay
                data =  json.loads(data.decode())
                if data['msg'] == 'success':
                    progress['value'] = 100  # Update the progress bar
                    # Update the status label and stop the progress bar
                    status_label.config(text="Download Complete")
                    break
                
                elif data['msg'] == 'failed':
                    status_label.config(text="Download Failed,\npress download to try again...")
                    submit_button.configure(state='noraml') 
                    break
                
                elif data['msg'] == 'update':
                    progress['value'] = int(data['number']) 
                    
                         
            os.close(read_pipe)
            os.close(write_pipe)
            self.reload_sessions(self.listbox)
            
        # Create a button to submit the download form
        submit_button = ttk.Button(form_frame, text="Download", command=lambda : download_bar(info_hash, name))
        submit_button.pack()

        # Hide the progress bar initially
        
        
        
    def download(self, info_hash : str, name : str, pipe : int) -> None:
        self.peer.download_file(info_hash, name, pipe)
        
    
    def create_torrent_window(self) -> None:

        file_path = filedialog.askopenfilename(parent=self)  
        
        if file_path:
            torrent_path = self.peer.create_torrent_file(file_path)
            with open(torrent_path,'r') as file:
                data = json.load(file)
            self.peer.announce(data['info_hash'],data['info']['name'] ,'')
        self.reload_sessions(self.listbox)
            
if __name__=='__main__':
    peer = PeerGUI()
    peer.mainloop()
    
