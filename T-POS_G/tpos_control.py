import customtkinter as ctk
from tkinter import ttk
import subprocess
import socket
import os
import threading
import time
import webbrowser
from tkinter import messagebox
import psutil
import logging
from datetime import datetime
import pyperclip 
import qrcode
from PIL import Image, ImageTk
import io

class VisitorInfo:
    def __init__(self, ip, timestamp, user_agent, method, path, status):
        self.ip = ip
        self.timestamp = timestamp
        self.user_agent = user_agent
        self.method = method
        self.path = path
        self.status = status

class TPOSControlApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("T-POS Control Panel")
        self.geometry("900x800")  # Diperbesar untuk QR Code
        self.minsize(500, 500)
        self.server_process = None
        self.loading = False
        self.port = 5000
        self.server_status = "stopped"
        self.log_lines = []
        self.qr_image = None
        self.visitors = []  # Untuk menyimpan daftar pengakses
        self.setup_ui_visitors()  # Tambahkan UI untuk menampilkan pengakses
        self.setup_logging()
        
        # UI Configuration
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        
        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.check_existing_process()

    def setup_ui_visitors(self):
        """Setup UI untuk menampilkan daftar pengakses"""
        self.visitors_frame = ctk.CTkFrame(self)
        self.visitors_frame.pack(pady=10, padx=10, fill="both", expand=True)
        
        visitors_label = ctk.CTkLabel(self.visitors_frame, text="Visitor Access Log:", font=("Arial", 12))
        visitors_label.pack(anchor="w")
        
        # Treeview untuk menampilkan data
        self.visitors_tree = ttk.Treeview(
            self.visitors_frame,
            columns=("IP", "Time", "Method", "Path", "Status", "User Agent"),
            show="headings",
            height=8
        )
        
        # Konfigurasi kolom
        self.visitors_tree.heading("IP", text="IP Address")
        self.visitors_tree.heading("Time", text="Time")
        self.visitors_tree.heading("Method", text="Method")
        self.visitors_tree.heading("Path", text="Path")
        self.visitors_tree.heading("Status", text="Status")
        self.visitors_tree.heading("User Agent", text="User Agent")
        
        self.visitors_tree.column("IP", width=120)
        self.visitors_tree.column("Time", width=120)
        self.visitors_tree.column("Method", width=70)
        self.visitors_tree.column("Path", width=150)
        self.visitors_tree.column("Status", width=70)
        self.visitors_tree.column("User Agent", width=200)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.visitors_frame, orient="vertical", command=self.visitors_tree.yview)
        self.visitors_tree.configure(yscrollcommand=scrollbar.set)
        
        self.visitors_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Tombol refresh
        btn_frame = ctk.CTkFrame(self.visitors_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=5)
        
        self.refresh_btn = ctk.CTkButton(
            btn_frame,
            text="Refresh",
            width=80,
            command=self.refresh_visitors
        )
        self.refresh_btn.pack(side="right")
        
        # Mulai thread untuk memantau log
        threading.Thread(target=self.monitor_access_log, daemon=True).start()

    def add_visitor(self, ip, user_agent):
        """Menambahkan pengakses baru ke daftar"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        visitor = VisitorInfo(ip, timestamp, user_agent)
        self.visitors.append(visitor)
        
        # Update UI
        self.visitors_tree.insert("", "end", values=(ip, timestamp, user_agent))
        self.visitors_tree.see("end")
        
        # Log aktivitas
        self.log(f"New visitor: {ip} ({user_agent})")

    def update_visitor_display(self, visitor):
        """Update tampilan treeview dengan pengakses baru"""
        self.visitors_tree.insert("", "end", values=(
            visitor.ip,
            visitor.timestamp,
            visitor.method,
            visitor.path,
            visitor.status,
            visitor.user_agent
        ))
        # Auto-scroll ke entri terbaru
        self.visitors_tree.see("end")
    
    def refresh_visitors(self):
        """Menyegarkan tampilan pengakses"""
        self.visitors_tree.delete(*self.visitors_tree.get_children())
        for visitor in self.visitors[-100:]:  # Tampilkan 100 entri terakhir
            self.visitors_tree.insert("", "end", values=(
                visitor.ip,
                visitor.timestamp,
                visitor.method,
                visitor.path,
                visitor.status,
                visitor.user_agent
            ))

    def setup_logging(self):
        logging.basicConfig(
            filename='tpos_control.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.log("Application started")

    def log(self, message, level="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_lines.append(log_entry)
        
        if level == "info":
            logging.info(message)
        elif level == "error":
            logging.error(message)
        
        if hasattr(self, 'log_text') and not hasattr(self, '_log_pending'):
            self._log_pending = True
            self.after(200, self._update_log_display)

    def _update_log_display(self):
        if hasattr(self, 'log_text'):
            self.log_text.configure(state="normal")
            self.log_text.insert("end", "\n".join(self.log_lines[-10:]) + "\n")
            self.log_text.configure(state="disabled")
            self.log_text.see("end")
        self._log_pending = False

    def create_widgets(self):
        # Header Frame
        header_frame = ctk.CTkFrame(self)
        header_frame.pack(pady=10, padx=10, fill="x")
        
        self.title_label = ctk.CTkLabel(header_frame, text="T-POS CONTROL PANEL", font=("Arial Black", 20))
        self.title_label.pack(pady=5)
        
        # Status Frame
        status_frame = ctk.CTkFrame(self)
        status_frame.pack(pady=10, padx=10, fill="x")
        
        self.status_indicator = ctk.CTkLabel(status_frame, text="●", font=("Arial", 14), text_color="red")
        self.status_indicator.pack(side="left", padx=5)
        
        self.status_label = ctk.CTkLabel(status_frame, text="Server Status: Stopped", font=("Arial", 12))
        self.status_label.pack(side="left")
        
        # Frame untuk IP dan tombol copy
        ip_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        ip_frame.pack(side="right", padx=10)
        
        self.ip_label = ctk.CTkLabel(ip_frame, text="", font=("Arial", 12))
        self.ip_label.pack(side="left")
        
        self.copy_ip_btn = ctk.CTkButton(
            ip_frame,
            text="Copy",
            width=50,
            command=self.copy_ip_to_clipboard,
            state="disabled"
        )
        self.copy_ip_btn.pack(side="left", padx=5)
        
        # Loading Frame
        self.loading_frame = ctk.CTkFrame(self)
        self.loading_label = ctk.CTkLabel(self.loading_frame, text="", font=("Arial", 12))
        self.loading_label.pack(pady=5)
        
        # QR Code Frame
        self.qr_frame = ctk.CTkFrame(self)
        self.qr_label = ctk.CTkLabel(self.qr_frame, text="")
        self.qr_label.pack(pady=10)
        
        # Button Frame
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(pady=10, fill="x", padx=20)
        
        self.start_btn = ctk.CTkButton(
            button_frame, 
            text="Start Server", 
            command=self.handle_start,
            fg_color="green",
            hover_color="dark green"
        )
        self.start_btn.pack(side="left", expand=True, padx=5)
        
        self.stop_btn = ctk.CTkButton(
            button_frame, 
            text="Stop Server", 
            command=self.stop_server, 
            state="disabled",
            fg_color="red",
            hover_color="dark red"
        )
        self.stop_btn.pack(side="left", expand=True, padx=5)
        
        self.open_btn = ctk.CTkButton(
            button_frame, 
            text="Open in Browser", 
            command=self.open_in_browser,
            state="disabled"
        )
        self.open_btn.pack(side="left", expand=True, padx=5)
        
        # Log Frame
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(pady=10, padx=10, fill="both", expand=True)
        
        log_label = ctk.CTkLabel(log_frame, text="Activity Log:", font=("Arial", 12))
        log_label.pack(anchor="w")
        
        self.log_text = ctk.CTkTextbox(log_frame, font=("Consolas", 10), wrap="none")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        
        # Add footer
        footer_frame = ctk.CTkFrame(self)
        footer_frame.pack(fill="x", padx=10, pady=5)
        
        version_label = ctk.CTkLabel(footer_frame, text="v1.1.0", font=("Arial", 10))
        version_label.pack(side="right")
    def generate_qr_code(self, url):
        """Generate QR Code image from URL"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=6,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to Tkinter compatible image
        img_tk = ImageTk.PhotoImage(img)
        return img_tk
    
    def update_qr_code(self):
        """Update QR Code display"""
        if self.server_status == "running":
            ip = self.get_local_ip()
            url = f"http://{ip}:{self.port}"
            self.qr_image = self.generate_qr_code(url)
            self.qr_label.configure(image=self.qr_image)
            self.qr_frame.pack()
        else:
            self.qr_frame.pack_forget()

    def copy_ip_to_clipboard(self):
        """Copy IP address to clipboard"""
        if self.server_status == "running":
            ip = self.get_local_ip()
            url = f"http://{ip}:{self.port}"
            pyperclip.copy(url)
            self.log("IP address copied to clipboard")
            # Beri feedback visual
            original_text = self.copy_ip_btn.cget("text")
            self.copy_ip_btn.configure(text="Copied!")
            self.after(2000, lambda: self.copy_ip_btn.configure(text=original_text))

    def check_existing_process(self):
        """Check if server is already running when app starts"""
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == 'main.exe':
                self.log("Found existing server process", "info")
                self.server_process = proc
                self.update_status("running")
                ip = self.get_local_ip()
                self.ip_label.configure(text=f"http://{ip}:{self.port}")
                self.open_btn.configure(state="normal")
                self.copy_ip_btn.configure(state="normal")
                break

    def update_status(self, status):
        self.server_status = status
        status_text = {
            "stopped": ("Server Status: Stopped", "red"),
            "starting": ("Server Status: Starting...", "orange"),
            "running": ("Server Status: Running", "green"),
            "stopping": ("Server Status: Stopping...", "orange")
        }
        
        text, color = status_text[status]
        self.status_label.configure(text=text)
        self.status_indicator.configure(text_color=color)
        
        # Update button states
        if status == "running":
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.open_btn.configure(state="normal")
            self.copy_ip_btn.configure(state="normal")
        elif status == "stopped":
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.open_btn.configure(state="disabled")
            self.copy_ip_btn.configure(state="disabled")
        else:  # starting/stopping
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled")
            self.open_btn.configure(state="disabled")
            self.copy_ip_btn.configure(state="disabled")

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            self.log(f"Error getting IP: {e}", "error")
            return "127.0.0.1"

    def is_port_in_use(self, port, timeout=1.0):
        """Check if port is in use with timeout"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex(('127.0.0.1', port)) == 0

    def is_our_process_using_port(self):
        """Check if our own process is using the port"""
        if not self.server_process:
            return False
            
        try:
            for conn in psutil.net_connections():
                if conn.laddr.port == self.port and conn.pid == self.server_process.pid:
                    return True
        except:
            pass
        return False

    def check_http_response(self):
        """Check if server responds to HTTP request"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(('127.0.0.1', self.port))
                s.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                data = s.recv(1024)
                return b"HTTP" in data
        except:
            return False

    def handle_start(self):
        if not os.path.exists("main.exe"):
            messagebox.showerror("Error", "main.exe not found in current directory!")
            self.log("main.exe not found", "error")
            return
            
        self.loading = True
        self.loading_frame.pack()
        self.update_status("starting")
        threading.Thread(target=self.start_server, daemon=True).start()
        threading.Thread(target=self.animate_loading, daemon=True).start()

    def animate_loading(self):
        dots = ""
        while self.loading:
            dots = "." if dots == "..." else dots + "."
            self.loading_label.configure(text=f"Starting server{dots}")
            time.sleep(0.5)

    def start_server(self):
        try:
            self.log("Attempting to start server...")
            
            if self.is_port_in_use(self.port):
                if not self.is_our_process_using_port():
                    messagebox.showwarning("Warning", f"Port {self.port} is already in use by another application!")
                    self.log(f"Port {self.port} already in use by other app", "error")
                    return
                else:
                    self.log("Port is used by our own process, continuing...")

            env = os.environ.copy()
            env["FLASK_ENV"] = "production"
            env["PYTHONUNBUFFERED"] = "1"

            with open("access_log.txt", "w") as f:
                f.write("")  # Kosongkan file
            
            self.server_process = subprocess.Popen(
                ["main.exe", "--access-log", "access_log.txt"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                cwd=os.getcwd(),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
                bufsize=1,
                universal_newlines=True,
                shell=True if os.name == 'nt' else False
            )
            threading.Thread(target=self.monitor_access_log, daemon=True).start()
            threading.Thread(target=self.monitor_server_startup, daemon=True).start()
            
        except Exception as e:
            self.log(f"Failed to start server: {str(e)}", "error")
            messagebox.showerror("Error", f"Failed to start server: {str(e)}")
            self.loading = False
            self.loading_frame.pack_forget()
            self.update_status("stopped")

    def monitor_access_log(self):
        """Memantau file log pengakses secara real-time"""
        last_position = 0
        log_file = "access_log.txt"
        
        while True:
            if self.server_status != "running":
                time.sleep(2)
                continue
                
            try:
                if not os.path.exists(log_file):
                    with open(log_file, "w") as f:
                        f.write("")
                    
                with open(log_file, "r") as f:
                    f.seek(last_position)
                    lines = f.readlines()
                    last_position = f.tell()
                    
                    for line in lines:
                        if line.strip():
                            try:
                                ip, timestamp, user_agent, method, path, status = line.strip().split("|", 5)
                                visitor = VisitorInfo(ip, timestamp, user_agent, method, path, status)
                                self.visitors.append(visitor)
                                self.after(0, self.update_visitor_display, visitor)
                            except ValueError:
                                continue
            except Exception as e:
                self.log(f"Error reading access log: {str(e)}", "error")
            
            time.sleep(3)  # Periksa setiap 3 detik
            
    def monitor_server_startup(self):
        start_time = time.time()
        timeout = 30
        
        while time.time() - start_time < timeout:
            if self.is_port_in_use(self.port):
                if self.check_http_response():
                    ip = self.get_local_ip()
                    self.after(0, self.on_server_started, ip)
                    return
                else:
                    self.log("Port is open but not responding to HTTP", "warning")
            
            if self.server_process.poll() is not None:
                self.log(f"Server process exited with code {self.server_process.returncode}", "error")
                self.after(0, self.on_server_timeout)
                return
                
            time.sleep(1)
        
        self.after(0, self.on_server_timeout)

    def on_server_started(self, ip):
        """Callback ketika server berhasil start"""
        self.ip_label.configure(text=f"http://{ip}:{self.port}")
        self.log(f"Server started successfully at http://{ip}:{self.port}")
        self.loading = False
        self.loading_frame.pack_forget()
        self.update_status("running")
        self.update_qr_code()

    def on_server_timeout(self):
        self.log("Server failed to start within timeout period", "error")
        messagebox.showerror("Error", "Server failed to start within timeout period")
        if self.server_process:
            self.server_process.kill()
            self.server_process = None
        self.loading = False
        self.loading_frame.pack_forget()
        self.update_status("stopped")

    def stop_server(self):
        if not self.server_process:
            return
            
        self.update_status("stopping")
        self.log("Attempting to stop server...")
        
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.server_process.pid)], 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL)
            else:
                self.server_process.terminate()
                try:
                    self.server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.server_process.kill()
                
            self.log("Server stopped successfully")
        except Exception as e:
            self.log(f"Error stopping server: {str(e)}", "error")
            messagebox.showerror("Error", f"Failed to stop server: {str(e)}")
        finally:
            self.server_process = None
            self.ip_label.configure(text="")
            self.update_status("stopped")

    def open_in_browser(self):
        if self.server_status == "running":
            ip = self.get_local_ip()
            url = f"http://{ip}:{self.port}"
            webbrowser.open_new(url)
            self.log(f"Opened {url} in browser")

    def on_closing(self):
        if self.server_status == "running":
            if messagebox.askyesno("Quit", "Server is still running. Do you want to stop it and quit?"):
                self.stop_server()
                self.destroy()
        else:
            self.destroy()

if __name__ == "__main__":
    app = TPOSControlApp()
    app.mainloop()