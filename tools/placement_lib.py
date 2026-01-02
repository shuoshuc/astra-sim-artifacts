import math
import numpy as np
from hilbertcurve.hilbertcurve import HilbertCurve


def coord_to_linear_index(x, y, z, dims):
    """
    Converts 3D coordinates to plane-major linear index.
    Convention: X is fastest changing, Z is slowest.
    Index = (z * L * W) + (y * W) + x
    """
    W_dim, L_dim, H_dim = dims
    return (z * L_dim * W_dim) + (y * W_dim) + x


class FirstFit:
    """
    First-Fit placement algorithm with 3D integral volume optimization.
    TODO: need to support wrap-around torus placements.
    """

    def __init__(self, W, L, H):
        self.W, self.L, self.H = W, L, H
        # Grid stores occupancy: 0 = free, 1 = occupied
        self.grid = np.zeros((W, L, H), dtype=int)

    def _get_integral_volume(self):
        """Creates a 3D prefix sum for O(1) volume checks."""
        return self.grid.cumsum(axis=0).cumsum(axis=1).cumsum(axis=2)

    def _is_free(self, integral, start, size):
        """Standard inclusion-exclusion for 3D range sum."""
        x, y, z = start
        A, B, C = size
        x1, y1, z1 = x + A - 1, y + B - 1, z + C - 1

        def get_val(i, j, k):
            if i < 0 or j < 0 or k < 0:
                return 0
            return integral[i, j, k]

        res = (
            get_val(x1, y1, z1)
            - get_val(x - 1, y1, z1)
            - get_val(x1, y - 1, z1)
            - get_val(x1, y1, z - 1)
            + get_val(x - 1, y - 1, z1)
            + get_val(x - 1, y1, z - 1)
            + get_val(x1, y - 1, z - 1)
            - get_val(x - 1, y - 1, z - 1)
        )
        return res == 0

    def find_placement(self, A, B, C):
        """Scans for the first origin that fits the AxBxC block."""
        integral = self._get_integral_volume()
        for z in range(self.H - C + 1):
            for y in range(self.L - B + 1):
                for x in range(self.W - A + 1):
                    if self._is_free(integral, (x, y, z), (A, B, C)):
                        return (x, y, z)
        return None

    def allocate(self, shape):
        """
        Allocates job and returns {job_linear_index: torus_linear_index}
        """
        A, B, C = shape
        origin = self.find_placement(A, B, C)

        if not origin:
            return None

        x0, y0, z0 = origin
        mapping = {}

        # Nested loops ordered by slowest to fastest changing (Z -> Y -> X)
        for c in range(C):
            for b in range(B):
                for a in range(A):
                    # 1. Physical coordinates in the WxLxH torus
                    px, py, pz = x0 + a, y0 + b, z0 + c

                    # 2. Update occupancy grid
                    self.grid[px, py, pz] = 1

                    # 3. Calculate linear indices (X is fastest)
                    job_idx = coord_to_linear_index(a, b, c, (A, B, C))
                    torus_idx = coord_to_linear_index(
                        px, py, pz, (self.W, self.L, self.H)
                    )

                    mapping[job_idx] = torus_idx

        return mapping


class SpaceFillingCurve:
    """
    Space Filling Curve (SFC) placement algorithm.
    Using Hilbert Curve as a specific implementation.
    """

    def __init__(self, W, L, H):
        self.W, self.L, self.H = W, L, H
        # Grid stores occupancy: 0 = free, 1 = occupied
        self.grid = np.zeros((W, L, H), dtype=int)

        # Calculate iterations P such that 2^P >= max(W, L, H)
        P = math.ceil(math.log2(max(W, L, H)))
        # Torus dimension is 3D.
        torus_dim = 3
        # Initialize Hilbert Curve with multiprocessing.
        self.sfc = HilbertCurve(P, torus_dim)

    def _fetch_availability(self):
        """
        Returns a sorted list of SFC indices for all free nodes in the grid.
        """
        # Get coordinates of free nodes
        free_coords = np.argwhere(self.grid == 0)
        # Get Hilbert indices
        distances = self.sfc.distances_from_points(free_coords)
        # Return sorted list
        return sorted(distances)

    def allocate(self, shape):
        """
        Allocates job and returns {job_linear_index: torus_linear_index}
        """
        A, B, C = shape
        # N is the total number of nodes required for the job
        N = A * B * C

        # Get all available Hilbert indices
        available_indices = self._fetch_availability()
        if len(available_indices) < N:
            return None

        # Allocate the first N available nodes that are closest together
        # and convert back to coordinates.
        alloc_coords = self.sfc.points_from_distances(available_indices[:N])

        mapping = {}
        # Job-internal node index is already linearized as i. It maps to the
        # linearized torus index from the allocated coordinates.
        for i in range(N):
            x, y, z = alloc_coords[i]
            # Mark as occupied
            self.grid[x, y, z] = 1
            # Map to torus index
            mapping[i] = coord_to_linear_index(x, y, z, (self.W, self.L, self.H))

        return mapping


class L1Clustering:
    """
    L1 Clustering placement algorithm (MC1x1).
    Minimizes the sum of L1 distances from a center node on a torus.
    """

    def __init__(self, W, L, H):
        self.W, self.L, self.H = W, L, H
        self.dims = np.array([W, L, H])
        # Grid stores occupancy: 0 = free, 1 = occupied
        self.grid = np.zeros((W, L, H), dtype=int)

        # Precompute coordinates for distance calculations
        x, y, z = np.indices((W, L, H))
        self.coords = np.stack((x, y, z), axis=-1).reshape(-1, 3)

    def _get_torus_distance(self, center_coord):
        diff = np.abs(self.coords - center_coord)
        dist_per_dim = np.minimum(diff, self.dims - diff)
        return np.sum(dist_per_dim, axis=1)

    def allocate(self, shape):
        A, B, C = shape
        k = A * B * C

        # Find idle nodes
        idle_indices = np.where(self.grid.flatten() == 0)[0]

        if len(idle_indices) < k:
            return None

        best_cost = float("inf")
        best_selection = None

        # Optimization: check subset of idle nodes
        step = max(1, len(idle_indices) // 100)

        for center_idx in idle_indices[::step]:
            center_coord = self.coords[center_idx]
            distances = self._get_torus_distance(center_coord)

            # We only care about distances to idle nodes
            idle_distances = distances[idle_indices]

            # Find k closest idle nodes
            if len(idle_distances) == k:
                k_closest_local_idx = np.arange(k)
            else:
                k_closest_local_idx = np.argpartition(idle_distances, k - 1)[:k]

            current_cost = np.sum(idle_distances[k_closest_local_idx])

            if current_cost < best_cost:
                best_cost = current_cost
                best_selection = idle_indices[k_closest_local_idx]

        if best_selection is None:
            return None

        mapping = {}
        # Sort selection to have deterministic mapping
        best_selection = sorted(best_selection)

        for i, idx in enumerate(best_selection):
            x, y, z = self.coords[idx]
            self.grid[x, y, z] = 1
            torus_idx = coord_to_linear_index(x, y, z, (self.W, self.L, self.H))
            mapping[i] = int(torus_idx)

        return mapping
