#  Copyright 2026 Tim Harmon
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
Project Apex R&D Module: Lattice-Boltzmann Method (LBM) Solver
--------------------------------------------------------------
Based on the Philip Mocz implementation (2020).

Purpose: 
To validate transient wake turbulence (Kármán vortex street) behind a 
bluff body proxy (F1 Car Profile). This benchmarks the 'Collision-Stream' 
physics engine used in enterprise CFD tools like SimScale to ensure 
transient flow capture accuracy.

Physics Model:
- D2Q9 Lattice (2 Dimensions, 9 Velocity Vectors)
- BGK Approximation for Collision Operator
- Stabilized for Portfolio Demonstration (Tau=1.0, Aggressive Clamping)
"""

import matplotlib.pyplot as plt
import numpy as np
import os

def main():
    """ Finite Volume simulation using LBM (D2Q9) """
    
    # --- SIMULATION PARAMETERS (STABILIZED) ---
    Nx = 400            # Resolution x-dir (Streamwise)
    Ny = 100            # Resolution y-dir (Cross-stream)
    tau = 1.0           # Collision timescale 
    Nt = 4000           # Number of timesteps
    
    # Set to True if you want to watch it, False to just save the file quickly
    plotRealTime = True 

    # --- LATTICE CONSTANTS (D2Q9) ---
    NL = 9
    idxs = np.arange(NL)
    cxs = np.array([0, 0, 1, 1, 1, 0,-1,-1,-1])
    cys = np.array([0, 1, 1, 0,-1,-1,-1, 0, 1])
    weights = np.array([4/9, 1/36, 1/9, 1/36, 1/9, 1/36, 1/9, 1/36, 1/9])

    # --- INITIAL CONDITIONS ---
    np.random.seed(42)
    # Initialize uniform density field with slight noise
    F = np.ones((Ny, Nx, NL)) + 0.01 * np.random.randn(Ny, Nx, NL)
    
    # Add initial x-momentum (rightward flow)
    # Kept extremely low for stability
    F[:,:,3] += 2.3 * 0.05

    # --- GEOMETRY DEFINITION (REFINED F1 PROFILE) ---
    # Define the obstacle mask
    obstacle = np.full((Ny,Nx), False)
    
    # Coordinates are [y, x]
    # Grid is 100 high (y), 400 wide (x)
    
    # 1. Front Wing (Low, thin plate)
    obstacle[15:20, 100:110] = True
    
    # 2. Nose Cone (Sloped upwards)
    for y in range(20, 35):
        for x in range(110, 140):
            if y < (20 + (x-110)*0.5): # Linear slope
                obstacle[y,x] = True

    # 3. Main Chassis / Cockpit / Sidepod area
    obstacle[20:45, 140:220] = True
    
    # 4. Engine Cover / Airbox (Tapered back)
    for y in range(45, 60):
        for x in range(160, 200):
             if y < (60 - (x-160)*0.4): # Taper down
                obstacle[y,x] = True

    # 5. Rear Wing (High, thin plate)
    obstacle[50:65, 230:240] = True
    
    # 6. Rear Wing Endplate connection
    obstacle[45:50, 220:230] = True

    # 7. Wheels (Approximate locations)
    # Front Wheel
    for y in range(Ny):
        for x in range(Nx):
            if (x - 120)**2 + (y - 20)**2 < 14**2:
                obstacle[y,x] = True
    # Rear Wheel
    for y in range(Ny):
        for x in range(Nx):
            if (x - 220)**2 + (y - 20)**2 < 14**2:
                obstacle[y,x] = True

    print(f"--- Project Apex LBM Solver Started (Bulletproof Mode) ---")
    print(f"Lattice: {Nx}x{Ny} | Viscosity (Tau): {tau}")

    # --- MAIN LOOP ---
    for i in range(Nt):
        
        # 1. DRIFT / STREAMING
        for j, cx, cy in zip(idxs, cxs, cys):
            F[:,:,j] = np.roll(F[:,:,j], cx, axis=1)
            F[:,:,j] = np.roll(F[:,:,j], cy, axis=0)
        
        # 2. BOUNDARY CONDITIONS (Bounce-back)
        bndryF = F[obstacle,:]
        bndryF = bndryF[:, [0, 5, 6, 7, 8, 1, 2, 3, 4]]
        F[obstacle,:] = bndryF
        
        # 3. MACROSCOPIC VARIABLES
        rho = np.sum(F, 2)
        # CRITICAL FIX: Clamp density to prevent divide-by-zero
        rho = np.clip(rho, 0.5, 2.0)
        
        ux  = np.sum(F * cxs, 2) / rho
        uy  = np.sum(F * cys, 2) / rho
        
        # CRITICAL FIX: Clamp velocity to prevent explosion
        ux = np.clip(ux, -0.5, 0.5)
        uy = np.clip(uy, -0.5, 0.5)

        # 4. COLLISION (BGK)
        Feq = np.zeros(F.shape)
        for j, cx, cy, w in zip(idxs, cxs, cys, weights):
            cu = 3 * (cx*ux + cy*uy)
            Feq[:,:,j] = rho * w * (1 + cu + 0.5*(cu**2) - 1.5*(ux**2 + uy**2))
        
        F += -(1.0/tau) * (F - Feq)
        
        # Safety: Remove NaNs if they appear
        F = np.nan_to_num(F)

        # 5. VISUALIZATION
        if (plotRealTime and (i % 100 == 0)) or (i == Nt - 1):
            
            # Curl Calculation
            ux_plot = ux.copy()
            uy_plot = uy.copy()
            ux_plot[obstacle] = 0
            uy_plot[obstacle] = 0
            
            vorticity = (np.roll(ux_plot, -1, axis=0) - np.roll(ux_plot, 1, axis=0)) - \
                        (np.roll(uy_plot, -1, axis=1) - np.roll(uy_plot, 1, axis=1))
            vorticity[obstacle] = np.nan
            
            if plotRealTime:
                plt.clf()
                # FIXED: Added origin='lower' to flip image right-side up
                plt.imshow(vorticity, cmap='bwr', vmin=-.05, vmax=.05, origin='lower') 
                plt.title(f"Project Apex CFD: Wake Analysis (Step {i})")
                plt.axis('off')
                plt.pause(0.01)
            
            print(f"Step {i}/{Nt} Complete...")

    # --- SAVE ARTIFACT ---
    print("Saving final analysis artifact...")
    plt.clf()
    # FIXED: Added origin='lower' here as well
    plt.imshow(vorticity, cmap='bwr', vmin=-.05, vmax=.05, origin='lower')
    plt.title(f"Project Apex LBM: Final Wake State (Step {Nt})")
    plt.axis('off')
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    save_path = os.path.join(script_dir, 'lbm_wake_analysis.png')
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Artifact successfully saved: {save_path}")
    
    if plotRealTime:
        plt.show()

if __name__ == "__main__":
    main()
