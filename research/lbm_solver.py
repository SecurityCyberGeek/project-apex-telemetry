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
bluff body proxy (simulating an aerodynamic element in free stream). 
This benchmarks the 'Collision-Stream' physics engine used in enterprise 
CFD tools like SimScale to ensure transient flow capture accuracy.

Physics Model:
- D2Q9 Lattice (2 Dimensions, 9 Velocity Vectors)
- BGK Approximation for Collision Operator
- Re (Reynolds Number) controlled via viscosity relaxation time (tau)
"""

import matplotlib.pyplot as plt
import numpy as np
import os

def main():
    """ Finite Volume simulation using LBM (D2Q9) """
    
    # --- SIMULATION PARAMETERS ---
    Nx = 400            # Resolution x-dir (Streamwise)
    Ny = 100            # Resolution y-dir (Cross-stream)
    rho0 = 100          # Average density
    tau = 0.6           # Collision timescale (kinematic viscosity)
    Nt = 4000           # Number of timesteps
    
    # Set to True to watch animation, False to just save final image (faster)
    plotRealTime = True 

    # --- LATTICE CONSTANTS (D2Q9) ---
    NL = 9
    idxs = np.arange(NL)
    # Velocity vectors (x, y)
    cxs = np.array([0, 0, 1, 1, 1, 0,-1,-1,-1])
    cys = np.array([0, 1, 1, 0,-1,-1,-1, 0, 1])
    # Weights for equilibrium distribution
    weights = np.array([4/9, 1/36, 1/9, 1/36, 1/9, 1/36, 1/9, 1/36, 1/9])

    # --- INITIAL CONDITIONS ---
    # F = Particle Distribution Function
    # Add random noise to initiate instability
    np.random.seed(42) # Fixed seed for reproducibility
    F = np.ones((Ny, Nx, NL)) + 0.01 * np.random.randn(Ny, Nx, NL)
    
    # Add initial x-momentum (rightward flow)
    F[:,:,3] += 2.3

    # --- GEOMETRY DEFINITION ---
    # Define a cylindrical obstacle (Bluff Body Proxy for Aero Element)
    obstacle = np.full((Ny,Nx), False)
    for y in range(Ny):
        for x in range(Nx):
            # Centered at (Nx/4, Ny/2) with radius 13
            if (x - Nx/4)**2 + (y - Ny/2)**2 < 13**2:
                obstacle[y,x] = True

    print(f"--- Project Apex LBM Solver Started ---")
    print(f"Grid: {Nx}x{Ny} | Steps: {Nt} | Re: Proportional to {(1/tau):.2f}")

    # --- MAIN LOOP ---
    for i in range(Nt):
        
        # 1. DRIFT / STREAMING
        # Move particles to neighboring lattice sites
        for j, cx, cy in zip(idxs, cxs, cys):
            F[:,:,j] = np.roll(F[:,:,j], cx, axis=1)
            F[:,:,j] = np.roll(F[:,:,j], cy, axis=0)
        
        # 2. BOUNDARY CONDITIONS
        # Reflective bounce-back on obstacle
        bndryF = F[obstacle,:]
        # Invert directions (e.g., East becomes West)
        # Based on D2Q9 indices: [0, 1, 2, 3, 4, 5, 6, 7, 8] -> [0, 5, 6, 7, 8, 1, 2, 3, 4]
        bndryF = bndryF[:, [0, 5, 6, 7, 8, 1, 2, 3, 4]]
        F[obstacle,:] = bndryF
        
        # 3. MACROSCOPIC VARIABLES
        rho = np.sum(F, 2)
        ux  = np.sum(F * cxs, 2) / rho
        uy  = np.sum(F * cys, 2) / rho
        
        # 4. COLLISION (BGK Relaxation)
        Feq = np.zeros(F.shape)
        for j, cx, cy, w in zip(idxs, cxs, cys, weights):
            # Dot product c*u
            cu = 3 * (cx*ux + cy*uy)
            Feq[:,:,j] = rho * w * (1 + cu + 0.5*(cu**2) - 1.5*(ux**2 + uy**2))
        
        F += -(1.0/tau) * (F - Feq)
        
        # 5. VISUALIZATION (Vorticity)
        if (plotRealTime and (i % 100 == 0)) or (i == Nt - 1):
            
            # Calculate Curl: dy/dx - dx/dy
            ux[obstacle] = 0
            uy[obstacle] = 0
            vorticity = (np.roll(ux, -1, axis=0) - np.roll(ux, 1, axis=0)) - \
                        (np.roll(uy, -1, axis=1) - np.roll(uy, 1, axis=1))
            vorticity[obstacle] = np.nan
            
            if plotRealTime:
                plt.clf()
                plt.imshow(vorticity, cmap='bwr', vmin=-.1, vmax=.1)
                plt.title(f"Project Apex LBM: Transient Wake Analysis (Step {i})")
                plt.axis('off')
                plt.pause(0.01)
            
            print(f"Step {i}/{Nt} Complete...")

    # --- SAVE ARTIFACT ---
    # Save the final state to disk for report generation
    print("Saving analysis artifact to 'lbm_wake_analysis.png'...")
    plt.clf()
    plt.imshow(vorticity, cmap='bwr', vmin=-.1, vmax=.1)
    plt.title(f"Project Apex LBM: Final Wake State (Step {Nt})")
    plt.axis('off')
    
    # Save to the same directory as the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    save_path = os.path.join(script_dir, 'lbm_wake_analysis.png')
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Artifact saved: {save_path}")
    
    if plotRealTime:
        plt.show()

if __name__ == "__main__":
    main()