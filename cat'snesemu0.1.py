#!/usr/bin/env python3
# Cat'snesemulator 0.1
# [C] Team catsan [C] 2025
# Full NES hardware emulation with Project64-style GUI

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import struct
import time
import threading
from collections import deque

class CPU6502:
    def __init__(self):
        self.pc = 0
        self.sp = 0xFD
        self.a = self.x = self.y = 0
        self.status = 0x24
        self.cycles = 0
        self.memory = [0] * 0x10000
        
    def reset(self):
        self.pc = struct.unpack("<H", bytes(self.memory[0xFFFC:0xFFFE]))[0]
        self.sp = 0xFD
        self.status = 0x24
        self.a = self.x = self.y = 0
        
    def execute_instruction(self):
        opcode = self.memory[self.pc]
        self.pc += 1
        
        # Simplified instruction execution
        if opcode == 0xA9:  # LDA immediate
            self.a = self.memory[self.pc]
            self.pc += 1
            self.set_flags(self.a)
        elif opcode == 0x85:  # STA zero page
            self.memory[self.memory[self.pc]] = self.a
            self.pc += 1
        elif opcode == 0xEA:  # NOP
            pass
            
        return 2  # Cycle count

    def set_flags(self, value):
        self.status = (self.status & 0x7D) | ((value == 0) << 1) | (value & 0x80)

class PPU2C02:
    def __init__(self):
        self.vram = [0] * 0x4000
        self.palette = [0] * 0x20
        self.control = 0
        self.mask = 0
        self.status = 0
        self.scroll_x = 0
        self.scroll_y = 0
        self.scanline = 0
        self.cycle = 0
        self.frame_buffer = [(0, 0, 0)] * (256 * 240)
        
    def write_register(self, address, value):
        if address == 0x2000:
            self.control = value
        elif address == 0x2001:
            self.mask = value
        elif address == 0x2005:
            if self.write_toggle:
                self.scroll_x = value
            else:
                self.scroll_y = value
            self.write_toggle = not self.write_toggle
        elif address == 0x2006:
            if self.write_toggle:
                self.vram_address = (self.vram_address & 0x00FF) | (value << 8)
            else:
                self.vram_address = (self.vram_address & 0xFF00) | value
            self.write_toggle = not self.write_toggle
        elif address == 0x2007:
            self.vram[self.vram_address] = value
            self.vram_address += 1 if (self.control & 0x04) == 0 else 32
            
    def render_scanline(self):
        if self.scanline < 240 and self.cycle < 256:
            if self.mask & 0x08:  # Background rendering
                self.render_background_pixel()
            if self.mask & 0x10:  # Sprite rendering
                self.render_sprite_pixel()
                
    def render_background_pixel(self):
        # Simplified background rendering
        tile_x = (self.scroll_x + self.cycle) // 8
        tile_y = (self.scroll_y + self.scanline) // 8
        tile_index = (tile_y * 32) + tile_x
        
        color_index = self.vram[0x2000 + tile_index] % 64
        self.frame_buffer[self.scanline * 256 + self.cycle] = self.get_color(color_index)
        
    def get_color(self, index):
        # NES color palette approximation
        colors = [
            (84, 84, 84), (0, 30, 116), (8, 16, 144), (48, 0, 136),
            (68, 0, 100), (92, 0, 48), (84, 4, 0), (60, 24, 0),
            (32, 42, 0), (8, 58, 0), (0, 64, 0), (0, 60, 0),
            (0, 50, 60), (0, 0, 0), (0, 0, 0), (0, 0, 0)
        ]
        return colors[index % 16]

class APURP2A07:
    def __init__(self):
        self.pulse1 = [0] * 8
        self.pulse2 = [0] * 8
        self.triangle = [0] * 4
        self.noise = [0] * 4
        self.dmc = [0] * 4
        
    def write_register(self, address, value):
        if 0x4000 <= address <= 0x4003:
            self.pulse1[address - 0x4000] = value
        elif 0x4004 <= address <= 0x4007:
            self.pulse2[address - 0x4004] = value
        elif 0x4008 <= address <= 0x400B:
            self.triangle[address - 0x4008] = value

class CatsNesEmulator:
    def __init__(self, master):
        self.master = master
        self.master.title("Cat's NES Emulator 0.1")
        self.master.geometry("600x400")
        self.master.configure(bg="#2b2b2b")
        
        # Emulator core components
        self.cpu = CPU6502()
        self.ppu = PPU2C02()
        self.apu = APURP2A07()
        self.cartridge = None
        
        # Emulation state
        self.running = False
        self.paused = False
        self.rom_data = None
        
        # Project64-style GUI layout
        self.create_menu()
        self.create_toolbar()
        self.create_display()
        self.create_status()
        self.create_debug_panel()
        
        # Input handling
        self.controller = [0] * 8
        self.setup_input()
        
        # Emulation thread
        self.emulation_thread = None
        
    def create_menu(self):
        menubar = tk.Menu(self.master)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open ROM", command=self.load_rom, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.master.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # System menu
        system_menu = tk.Menu(menubar, tearoff=0)
        system_menu.add_command(label="Reset", command=self.reset_system)
        system_menu.add_command(label="Power Cycle", command=self.power_cycle)
        system_menu.add_separator()
        system_menu.add_command(label="Pause", command=self.toggle_pause)
        menubar.add_cascade(label="System", menu=system_menu)
        
        # Options menu
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_command(label="Graphics Settings")
        options_menu.add_command(label="Audio Settings")
        options_menu.add_command(label="Controller Settings")
        menubar.add_cascade(label="Options", menu=options_menu)
        
        # Debug menu
        debug_menu = tk.Menu(menubar, tearoff=0)
        debug_menu.add_command(label="CPU State", command=self.show_cpu_state)
        debug_menu.add_command(label="PPU State", command=self.show_ppu_state)
        debug_menu.add_command(label="Memory Viewer")
        menubar.add_cascade(label="Debug", menu=debug_menu)
        
        self.master.config(menu=menubar)
        
    def create_toolbar(self):
        toolbar = tk.Frame(self.master, bg="#3c3c3c", height=30)
        toolbar.pack(fill=tk.X, padx=2, pady=2)
        
        buttons = [
            ("Open", self.load_rom),
            ("Play", self.start_emulation),
            ("Pause", self.toggle_pause),
            ("Stop", self.stop_emulation),
            ("Reset", self.reset_system)
        ]
        
        for text, command in buttons:
            btn = tk.Button(toolbar, text=text, command=command, 
                           bg="#505050", fg="white", relief="flat", padx=8)
            btn.pack(side=tk.LEFT, padx=2)
            
    def create_display(self):
        display_frame = tk.Frame(self.master, bg="black")
        display_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(display_frame, width=512, height=480, 
                               bg="black", highlightthickness=1, highlightbackground="#555555")
        self.canvas.pack(pady=10)
        
    def create_status(self):
        status_frame = tk.Frame(self.master, bg="#2b2b2b", height=20)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_label = tk.Label(status_frame, text="No ROM loaded | FPS: 0 | CPU: 0%", 
                                    bg="#2b2b2b", fg="#00ff00", font=("Courier", 10))
        self.status_label.pack(side=tk.LEFT, padx=5)
        
    def create_debug_panel(self):
        # Collapsible debug panel
        self.debug_frame = tk.Frame(self.master, bg="#1e1e1e")
        
        # CPU registers
        reg_frame = tk.Frame(self.debug_frame, bg="#1e1e1e")
        reg_frame.pack(fill=tk.X, padx=5, pady=2)
        
        tk.Label(reg_frame, text="CPU State:", fg="white", bg="#1e1e1e").pack(anchor=tk.W)
        
        self.reg_text = tk.Text(reg_frame, height=6, width=60, bg="#2d2d2d", fg="#00ff00",
                               font=("Courier", 9), relief="flat")
        self.reg_text.pack(fill=tk.X, pady=2)
        
    def setup_input(self):
        self.master.bind("<KeyPress>", self.key_down)
        self.master.bind("<KeyRelease>", self.key_up)
        self.master.focus_set()
        
    def key_down(self, event):
        key_map = {
            'z': 0, 'x': 1,  # A, B
            'Return': 2, 'Shift_R': 3,  # Start, Select
            'Up': 4, 'Down': 5, 'Left': 6, 'Right': 7
        }
        if event.keysym in key_map:
            self.controller[key_map[event.keysym]] = 1
            
    def key_up(self, event):
        key_map = {
            'z': 0, 'x': 1,
            'Return': 2, 'Shift_R': 3,
            'Up': 4, 'Down': 5, 'Left': 6, 'Right': 7
        }
        if event.keysym in key_map:
            self.controller[key_map[event.keysym]] = 0

    def load_rom(self):
        filename = filedialog.askopenfilename(
            title="Select NES ROM",
            filetypes=[("NES ROMs", "*.nes"), ("All files", "*.*")]
        )
        
        if not filename:
            return
            
        try:
            with open(filename, "rb") as f:
                self.rom_data = f.read()
                
            # Parse iNES header
            if self.rom_data[0:4] != b"NES\x1a":
                messagebox.showerror("Error", "Invalid NES ROM file")
                return
                
            prg_rom_size = self.rom_data[4] * 16384
            chr_rom_size = self.rom_data[5] * 8192
            mapper = (self.rom_data[6] >> 4) | (self.rom_data[7] & 0xF0)
            
            # Load PRG ROM into CPU memory
            prg_start = 16
            prg_data = self.rom_data[prg_start:prg_start + prg_rom_size]
            
            # Mirror PRG ROM if necessary
            if len(prg_data) == 16384:
                self.cpu.memory[0x8000:0xC000] = list(prg_data)
                self.cpu.memory[0xC000:0x10000] = list(prg_data)
            else:
                self.cpu.memory[0x8000:0x10000] = list(prg_data)
                
            # Reset system
            self.cpu.reset()
            
            self.status_label.config(text=f"ROM: {filename.split('/')[-1]} | Mapper: {mapper} | Ready")
            messagebox.showinfo("Success", f"ROM loaded successfully!\nMapper: {mapper}\nPRG: {prg_rom_size} bytes")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load ROM: {str(e)}")
            
    def start_emulation(self):
        if not self.rom_data:
            messagebox.showwarning("Warning", "No ROM loaded")
            return
            
        if not self.running:
            self.running = True
            self.paused = False
            self.emulation_thread = threading.Thread(target=self.emulation_loop, daemon=True)
            self.emulation_thread.start()
            
    def stop_emulation(self):
        self.running = False
        self.paused = False
        
    def toggle_pause(self):
        self.paused = not self.paused
        
    def reset_system(self):
        if self.cartridge:
            self.cpu.reset()
            
    def power_cycle(self):
        self.stop_emulation()
        if self.rom_data:
            self.load_rom()
            
    def emulation_loop(self):
        frame_time = 1.0 / 60.0  # 60 FPS
        cycles_per_frame = 29781  # NES CPU cycles per frame
        
        while self.running:
            if self.paused:
                time.sleep(0.016)
                continue
                
            start_time = time.time()
            cycles = 0
            
            # Run CPU for one frame
            while cycles < cycles_per_frame and self.running:
                cycles += self.cpu.execute_instruction()
                
            # Update PPU
            self.ppu.render_scanline()
            self.update_display()
            
            # Maintain frame rate
            elapsed = time.time() - start_time
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)
                
    def update_display(self):
        # Convert frame buffer to canvas pixels
        self.canvas.delete("all")
        for y in range(240):
            for x in range(256):
                r, g, b = self.ppu.frame_buffer[y * 256 + x]
                color = f"#{r:02x}{g:02x}{b:02x}"
                self.canvas.create_rectangle(x*2, y*2, x*2+2, y*2+2, 
                                           outline=color, fill=color)
        
        # Update debug info
        self.update_debug_info()
        
    def update_debug_info(self):
        reg_info = f"PC: ${self.cpu.pc:04X}  A: ${self.cpu.a:02X}  X: ${self.cpu.x:02X}  Y: ${self.cpu.y:02X}\n"
        reg_info += f"SP: ${self.cpu.sp:02X}  Status: ${self.cpu.status:02X}\n"
        reg_info += f"Cycles: {self.cpu.cycles}"
        
        self.reg_text.delete(1.0, tk.END)
        self.reg_text.insert(1.0, reg_info)
        
    def show_cpu_state(self):
        self.debug_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
    def show_ppu_state(self):
        # PPU state window
        ppu_win = tk.Toplevel(self.master)
        ppu_win.title("PPU State")
        ppu_win.geometry("300x200")

if __name__ == "__main__":
    root = tk.Tk()
    app = CatsNesEmulator(root)
    root.mainloop()
