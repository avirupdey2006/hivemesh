# FINAL SIH DEMO TEST GUIDE

### 1. Clean startup
```powershell
cd D:\sih-amr-fleet
.\launch.bat
```
*Wait for all terminal windows to open and the dashboard to launch in your browser at `http://localhost:8000/`.*

### 2. Verify Startup State
- Observe the **4 robots (R01-R04)** starting at their respective base stations.
- Verify the header displays **MQTT: OFFLINE** (if Mosquitto is absent) and **UDP: ACTIVE**.
- Confirm that the robots begin executing their autonomous missions (AUTO DEMO mode).

### 3. Verify Dynamic Obstacle (Chaos)
- Click the **Drop Obstacle (D* Lite)** button.
- **Expected:** A bright red/orange `⚠` warning block should instantly appear on the warehouse grid ahead of a robot.
- **Expected:** The affected robot should instantly calculate a new route, avoiding the obstacle, and the new route path will update visually.

### 4. Verify Spoof Attack (Security)
- Click the **Simulate Spoof Attack** button.
- **Expected:** The targeted robot (usually R02) will immediately turn dark red to indicate `SPOOFED` status.
- **Expected:** Its visual position will clamp to the edge of the grid if the spoofed coordinates fall outside the warehouse bounds.
- **Expected:** A security alert will populate in the Event Feed and Audit Ledger, demonstrating the anomaly detection catching the spoofed coordinate `(x+12, y+12)`.

### 5. Verify Reset Warehouse
- Click the newly added **RESET WAREHOUSE** button below the chaos controls.
- Confirm the prompt dialogue.
- **Expected:** All robots instantly return to their starting grid configurations `(2,2), (27,2), (2,17), (27,17)`.
- **Expected:** Battery levels restore to 100% / initial levels.
- **Expected:** Dynamic obstacles clear from the grid.
- **Expected:** The entire simulation resumes cleanly without requiring a restart of Python, the Observer, or the browser.

### 6. Verify Manual Control
- Click **MANUAL CONTROL** on the mode toggle.
- Click a robot on the map (e.g. `R01`).
- Click a valid open space on the grid.
- **Expected:** The robot immediately plots a path and physically navigates to the destination via UDP commands.
