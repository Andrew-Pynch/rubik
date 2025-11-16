from world import World

w = World()
for i in range(10):
    w.set_cell(i, i * 2, "X")
w.render()
