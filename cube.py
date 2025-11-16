from faces import Face, SOLVED_FACES, FACE_OFFSETS
from world import World

world = World()

class CubeState:
    def __init__(self):
        self.origin_row = world.height // 2
        self.origin_col = world.width // 2
        self.spacing = 2
        self.faces = self.init_faces(SOLVED_FACES)

    def init_faces(self, initial_faces):
        faces = {}

        # Loop over each face (FRONT, BACK, etc.)
        for face in initial_faces:
            original_grid = initial_faces[face]

            # make a new 3x3 grid for this face
            new_grid = []

            # Loop over each row of the original grid
            for row in original_grid:
                new_row = []
                for color in row:
                    new_row.append(color)
                new_grid.append(new_row)

            # after copying all rows, store the new grid
            faces[face] = new_grid

        return faces

    def render(
            self,
            world: World, 
            face: Face, 
            origin_row: int, 
            origin_col: int
    ):
        for face in self.faces:
            (dr, dc) = FACE_OFFSETS[face]
            face_origin_row = origin_row + dr
            face_origin_col = origin_col + dc * self.spacing
            self.render_face_into_world(world, face, face_origin_row, face_origin_col)

    def render_face_into_world(
            self, 
            world: World, 
            face: Face, 
            origin_row: int, 
            origin_col: int
    ):
        for r, row in enumerate(self.faces[face]):
            for c, cell in enumerate(row):
                world_row = origin_row + r
                world_col = origin_col + (c * self.spacing)
                world.set_cell(world_row, world_col, str(cell))

cube = CubeState()
cube.render(world, Face.FRONT, cube.origin_row, cube.origin_col)
world.render()
