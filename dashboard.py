#This dashboard was developed by Aiden Ware Bosanko
import serial
import matplotlib.pyplot as plt
import pandas as pd
import tkinter as tk
import random


class CyberSplash:
    def __init__(self, root, on_complete):
        self.root = root
        self.on_complete = on_complete
        
        # Create the blank canvas for our animation
        self.canvas = tk.Canvas(root, width=800, height=600, bg="black", highlightthickness=0)
        self.canvas.pack()
        
        # Engine Variables
        self.chars = []
        self.phase = 1
        self.state = "falling" # States: 'falling', 'waiting', 'clearing'
        self.wait_timer = 0
        
        # Start Phase 1
        self.setup_text("made by aiden ware bosanko")
        self.animate()

    def setup_text(self, text):
        self.chars = []
        text = text.upper()
        char_width = 24
        total_width = len(text) * char_width
        start_x = (800 - total_width) // 2
        
        for i, char in enumerate(text):
            if char == " ":
                continue # Skip spaces
            
            # Start high above the screen at random heights for a staggered waterfall effect
            start_y = random.randint(-500, -50)
            
            # Spawn the text object on the canvas
            cid = self.canvas.create_text(
                start_x + (i * char_width), start_y, 
                text="#", fill="#00ffcc", font=("Courier", 22, "bold")
            )
            
            # Store its specific rules
            self.chars.append({
                "id": cid,
                "target_char": char,
                "target_y": 300, # The center of the screen
                "locked": False,
                "speed": random.randint(15, 25)
            })

    def animate(self):
        if self.state == "falling":
            all_locked = True
            for c in self.chars:
                if not c["locked"]:
                    all_locked = False
                    self.canvas.move(c["id"], 0, c["speed"])
                    coords = self.canvas.coords(c["id"])
                    
                    if coords[1] >= c["target_y"]:
                        # It hit the center! Lock it in place.
                        self.canvas.coords(c["id"], coords[0], c["target_y"])
                        self.canvas.itemconfig(c["id"], text=c["target_char"], fill="white")
                        c["locked"] = True
                    else:
                        # Matrix scramble effect while it falls
                        self.canvas.itemconfig(c["id"], text=random.choice(["#", "*", "X", "0", "1"]))
                        
            if all_locked:
                self.state = "waiting"
                self.wait_timer = 30 # Pause so you can read it

        elif self.state == "waiting":
            self.wait_timer -= 1
            if self.wait_timer <= 0:
                self.state = "clearing"
                # Assign new random speeds so they splash away at different rates
                for c in self.chars:
                    c["speed"] = random.randint(15, 40)

        elif self.state == "clearing":
            all_cleared = True
            for c in self.chars:
                self.canvas.move(c["id"], 0, c["speed"])
                # Check if it has fallen off the bottom of the screen
                if self.canvas.coords(c["id"])[1] < 650:
                    all_cleared = False
                    
            if all_cleared:
                self.canvas.delete("all") # Wipe the board clean
                if self.phase == 1:
                    # Trigger Phase 2!
                    self.phase = 2
                    self.state = "falling"
                    self.setup_text("PROPELLER DYNA PRO")
                else:
                    # Animation completely finished. Close splash and launch main app.
                    self.root.destroy()
                    self.on_complete()
                    return

        # Loop this exact function again in 40 milliseconds
        self.root.after(40, self.animate)

# ==========================================
# THIS IS WHERE YOU WILL BUILD YOUR DASHBOARD
# ==========================================
def launch_dashboard():
    main_app = tk.Tk()
    main_app.title("Propeller Dyna Pro - Control Center")
    main_app.geometry("800x600")
    main_app.configure(bg="#1e1e1e")
    
    tk.Label(
        main_app, 
        text="Aiden, the keyboard is yours. Let's build the GUI.", 
        fg="#00ffcc", bg="#1e1e1e", font=("Helvetica", 16)
    ).pack(pady=250)
    
    main_app.mainloop()

# ==========================================
# BOOT SEQUENCE
# ==========================================
if __name__ == "__main__":
    splash = tk.Tk()
    splash.title("Loading...")
    splash.geometry("800x600")
    splash.configure(bg="black")
    splash.overrideredirect(True) # Removes standard Windows borders
    
    # Center the window exactly on your monitor
    sw = splash.winfo_screenwidth()
    sh = splash.winfo_screenheight()
    splash.geometry(f"800x600+{int(sw/2-400)}+{int(sh/2-300)}")
    
    # Launch the animation class, and tell it what to run when it finishes
    app = CyberSplash(splash, launch_dashboard)
    splash.mainloop()



