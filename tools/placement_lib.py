import numpy as np


class FirstFit:
    """
    First-Fit placement algorithm with 3D integral volume optimization.
    TODO: need to support wrap-around torus placements.
    """

    def __init__(self, W, L, H):
        self.W, self.L, self.H = W, L, H
        # Grid stores occupancy: 0 = free, 1 = occupied
        self.grid = np.zeros((W, L, H), dtype=int)

    def _get_linear_index(self, x, y, z, dims):
        """
        Converts 3D coordinates to plane-major linear index.
        Convention: X is fastest changing, Z is slowest.
        Index = (z * L * W) + (y * W) + x
        """
        W_dim, L_dim, H_dim = dims
        return (z * L_dim * W_dim) + (y * W_dim) + x

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
                    job_idx = self._get_linear_index(a, b, c, (A, B, C))
                    torus_idx = self._get_linear_index(
                        px, py, pz, (self.W, self.L, self.H)
                    )

                    mapping[job_idx] = torus_idx

        return mapping
