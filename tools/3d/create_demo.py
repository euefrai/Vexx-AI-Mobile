"""Reproduce the original CC0 cube: 24 vertices, 12 triangles, no dependencies."""
import json
import struct
from pathlib import Path

faces = [
    ([(1,-1,-1),(1,1,-1),(1,1,1),(1,-1,1)], (1,0,0)),
    ([(-1,-1,1),(-1,1,1),(-1,1,-1),(-1,-1,-1)], (-1,0,0)),
    ([(-1,1,-1),(-1,1,1),(1,1,1),(1,1,-1)], (0,1,0)),
    ([(-1,-1,1),(-1,-1,-1),(1,-1,-1),(1,-1,1)], (0,-1,0)),
    ([(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)], (0,0,1)),
    ([(1,-1,-1),(-1,-1,-1),(-1,1,-1),(1,1,-1)], (0,0,-1)),
]
positions, normals, indices = [], [], []
for corners, normal in faces:
    start = len(positions)//3
    for corner in corners:
        positions.extend(corner)
        normals.extend(normal)
    indices.extend(start+i for i in (0,1,2,0,2,3))
binary = struct.pack('<72f72f36H', *positions, *normals, *indices)
doc = {'asset':{'version':'2.0','generator':'Vexx AI original CC0 cube'}, 'scene':0,
       'scenes':[{'nodes':[0]}], 'nodes':[{'mesh':0,'name':'Cubo'}],
       'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':1},'indices':2,'material':0}]}],
       'materials':[{'pbrMetallicRoughness':{'baseColorFactor':[.55,.61,.97,1],'metallicFactor':0,'roughnessFactor':.6}}],
       'buffers':[{'byteLength':len(binary)}],
       'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':288}, {'buffer':0,'byteOffset':288,'byteLength':288}, {'buffer':0,'byteOffset':576,'byteLength':72}],
       'accessors':[{'bufferView':0,'componentType':5126,'count':24,'type':'VEC3','min':[-1,-1,-1],'max':[1,1,1]},
                    {'bufferView':1,'componentType':5126,'count':24,'type':'VEC3'},
                    {'bufferView':2,'componentType':5123,'count':36,'type':'SCALAR'}]}
body = json.dumps(doc,separators=(',',':')).encode()
body += b' ' * (-len(body) % 4)
data = struct.pack('<III',0x46546c67,2,28+len(body)+len(binary)) + struct.pack('<II',len(body),0x4e4f534a) + body + struct.pack('<II',len(binary),0x004e4942) + binary
target = Path(__file__).resolve().parents[2]/'public/models/demo-cube.glb'
target.write_bytes(data)
print(f'{target.name}: {len(data)} bytes')
