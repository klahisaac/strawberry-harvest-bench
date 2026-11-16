"""Cycles RGB-D renders of strawberries in a greenhouse, for a berry detector.

Ported from the Codex-written renderer of the first version
(robot-strawberry-v1/src/simulation_data_genearator/blender_renderer.py):
the same berries with real achene geometry, serrated veined leaves, gutter,
soil, greenhouse framing and lighting. Changed here:

  - no robot: the cutter, gripper and collection tray are gone
  - any number of berries per image, each with its own size and ripeness
  - 640 x 640, and a mask of which berry each pixel shows, for box labels

Scene coordinates are the camera's optical frame, in metres: x to the right,
y down, z forward (away from the camera). The gutter runs along x above and
behind the berries.

Each render writes an RGB PNG (8 bits per channel) and a depth PNG (16 bits,
1 unit = 1 mm along the optical axis, 0 = no hit), and returns the berry
index of every pixel (0 = none).
"""

import dataclasses
import math
import pathlib
import tempfile

import bpy
import mathutils
import numpy as np
import OpenEXR
from PIL import Image as pil_image

WIDTH = HEIGHT = 640
FOCAL_PX = 600.0  # focal length in pixels, the same along x and y
MAX_DEPTH_M = 20.0
RIPE_MIN = 0.6  # a berry at or above this ripeness is worth picking
CAMERA_AT = (0.04, 0.06, 0.15)  # the default camera position, as in the first version
PROTOTYPE_RADIUS = 0.023  # the half width of the berry mesh at scale 1


@dataclasses.dataclass
class Berry:
    """One berry: where its centre is, how big and how ripe."""

    x: float
    y: float  # down is +y
    z: float  # away from the camera is +z
    radius: float  # half the width, metres
    ripeness: float  # 0 = green, 1 = fully red
    stem_top: tuple[float, float, float] | None = None  # where the stem joins the plant
    shape: int = 0  # which of the prototype berry shapes

    @property
    def scale(self) -> float:
        return self.radius / PROTOTYPE_RADIUS

    @property
    def top(self) -> tuple[float, float, float]:
        """Where the stem leaves the fruit, above the calyx."""
        return (self.x, self.y - 0.030 * self.scale, self.z)


def camera_intrinsics() -> dict:
    """The pinhole model every render uses, for whoever reads the depth."""
    return {
        "width": WIDTH, "height": HEIGHT,
        "fx": FOCAL_PX, "fy": FOCAL_PX,
        "cx": (WIDTH - 1) / 2, "cy": (HEIGHT - 1) / 2,
        "depth_unit_m": 0.001,
        "depth_axis": "optical axis (z), 0 = no hit",
    }


def berry_color(ripeness: float) -> tuple[float, float, float]:
    """Skin colour: green, white, pink, then the red of the first version."""
    stops = [
        (0.00, (0.13, 0.28, 0.035)),
        (0.25, (0.34, 0.44, 0.13)),
        (0.40, (0.62, 0.60, 0.42)),
        (0.55, (0.66, 0.26, 0.17)),
        (0.75, (0.48, 0.012, 0.018)),
        (1.00, (0.30, 0.006, 0.010)),
    ]
    for (r0, c0), (r1, c1) in zip(stops, stops[1:]):
        if ripeness <= r1:
            t = (max(ripeness, r0) - r0) / (r1 - r0)
            return tuple(a + (b - a) * t for a, b in zip(c0, c1))
    return stops[-1][1]


def achene_color(ripeness: float) -> tuple[float, float, float]:
    if ripeness < 0.4:
        return (0.20, 0.30, 0.07)  # green
    return (0.42, 0.24, 0.065)  # golden, as in the first version


# ---- building blocks (from the first version) -------------------------------------


def material(name, color, roughness=.4, metallic=0, organic=False):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    if organic:
        bsdf.inputs['Subsurface Weight'].default_value = .075
        bsdf.inputs['Subsurface Radius'].default_value = (.0012, .0006, .0003)
        tex = mat.node_tree.nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = 38
        tex.inputs['Detail'].default_value = 3
        ramp = mat.node_tree.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color = tuple(v*.35 for v in color)+(1,)
        ramp.color_ramp.elements[1].color = tuple(min(1, v*1.3) for v in color)+(1,)
        mat.node_tree.links.new(tex.outputs['Fac'], ramp.inputs[0])
        mat.node_tree.links.new(ramp.outputs[0], bsdf.inputs['Base Color'])
        bump = mat.node_tree.nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = .15
        bump.inputs['Distance'].default_value = .00016
        mat.node_tree.links.new(tex.outputs['Fac'], bump.inputs['Height'])
        mat.node_tree.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def mesh_object(name, vertices, faces, mat, parent=None, collection=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.collection).objects.link(obj)
    if mat:
        mesh.materials.append(mat)
    obj.parent = parent
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


def empty(name, location=(0, 0, 0), collection=None):
    obj = bpy.data.objects.new(name, None)
    (collection or bpy.context.collection).objects.link(obj)
    obj.location = location
    return obj


def box(name, location, size, mat, bevel=.001, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    obj.parent = parent
    if bevel:
        mod = obj.modifiers.new('machined edges', 'BEVEL')
        mod.width, mod.segments = bevel, 3
        obj.modifiers.new('weighted normals', 'WEIGHTED_NORMAL')
    return obj


def tube(name, points, radius, mat, parent=None, collection=None):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 8
    curve.bevel_depth, curve.bevel_resolution = radius, 3
    poly = curve.splines.new('POLY')
    poly.points.add(len(points)-1)
    for p, co in zip(poly.points, points):
        p.co = (*co, 1)
    obj = bpy.data.objects.new(name, curve)
    (collection or bpy.context.collection).objects.link(obj)
    obj.data.materials.append(mat)
    obj.parent = parent
    return obj


def leaf(name, origin, length, width, angle, mats, parent=None, collection=None):
    root = empty(name, origin, collection)
    root.parent = parent
    root.rotation_euler = (.25, -.2, angle)
    verts, faces = [], []
    count = 24
    for i in range(count+1):
        u = i/count
        w = width * math.sin(math.pi*u)**.8 * (1.0 if i % 2 else .86)
        for side in [-1, 0, 1]:
            verts.append((side*w, -length*u, .006*math.sin(math.pi*u)+abs(side)*.003*math.sin(math.pi*u)))
    for i in range(count):
        for j in range(2):
            k = 3*i+j
            faces.append((k, k+1, k+4, k+3))
    mesh_object(name+'_surface', verts, faces, mats['leaf'], root, collection)
    tube('midrib', [(0, -length*u, .006*math.sin(math.pi*u)-.00035) for u in np.linspace(0, 1, 16)], .00035,
         mats['vein'], root, collection)
    for u in np.linspace(.16, .82, 6):
        for side in [-1, 1]:
            v = min(1, u+.12)
            tube('leaf vein', [(0, -length*u, .006*math.sin(math.pi*u)-.0004),
                               (side*width*math.sin(math.pi*v)**.8*.87, -length*v, .008*math.sin(math.pi*v)-.0004)],
                 .00012, mats['vein'], root, collection)
    return root


def berry_prototype(name, mats, seed, collection):
    """The first version's berry: broad shoulders, tapered tip, achenes in dimples, calyx."""
    root = empty(name, (0, 0, 0), collection)
    seed_uv = []
    rng = np.random.default_rng(seed)
    for row, theta in enumerate(np.linspace(.34, 2.82, 15)):
        n = max(6, int(32*math.sin(theta)*(1+.25*math.cos(theta))))
        for j in range(n):
            seed_uv.append((theta+rng.uniform(-.025, .025), 2*math.pi*(j+.5*(row % 2))/n+rng.uniform(-.025, .025)))
    shoulder = rng.uniform(.22, .32)  # shape varies a little between prototypes
    length = rng.uniform(.031, .036)

    def surface(theta, phi):
        radius = .023*math.sin(theta)*(1+shoulder*math.cos(theta))
        return np.array([radius*math.cos(phi), -length*math.cos(theta), radius*math.sin(phi)])

    def normal(theta, phi):
        a = surface(theta+.0001, phi)-surface(theta-.0001, phi)
        b = surface(theta, phi+.0001)-surface(theta, phi-.0001)
        n = np.cross(a, b)
        if n[0]*math.cos(phi)+n[2]*math.sin(phi) < 0:
            n = -n
        return n/np.linalg.norm(n)

    verts, faces = [], []
    nt, np_ = 80, 112
    for i in range(nt+1):
        theta = max(.0001, min(math.pi-.0001, math.pi*i/nt))
        for j in range(np_):
            phi = 2*math.pi*j/np_
            p = surface(theta, phi)
            indent = 0
            for st, sp in seed_uv:
                dt = (theta-st)*.030
                if abs(dt) > .002:
                    continue
                dp = math.atan2(math.sin(phi-sp), math.cos(phi-sp))*.023*math.sin(theta)
                indent += .00048*math.exp(-(dt/.0011)**2-(dp/.0008)**2)
            p -= normal(theta, phi)*indent
            verts.append(p.tolist())
    for i in range(nt):
        for j in range(np_):
            a = i*np_+j
            b = i*np_+(j+1) % np_
            faces.append((a, b, b+np_, a+np_))
    mesh_object(name+'_flesh', verts, faces, mats['fruit'], root, collection)
    # Hundreds of actual achene geometries, merged into one mesh.
    verts, faces = [], []
    for theta, phi in seed_uv:
        p = surface(theta, phi)
        n = normal(theta, phi)
        tangent = surface(theta+.001, phi)-surface(theta-.001, phi)
        tangent /= np.linalg.norm(tangent)
        across = np.cross(n, tangent)
        p -= n*.00025
        offset = len(verts)
        for i in range(7):
            a = math.pi*i/6
            for j in range(8):
                b = 2*math.pi*j/8
                q = p+tangent*(.00083*math.cos(a))+across*(.00036*math.sin(a)*math.cos(b))+n*(.00027*math.sin(a)*math.sin(b))
                verts.append(q.tolist())
        for i in range(6):
            for j in range(8):
                a = offset+i*8+j
                b = offset+i*8+(j+1) % 8
                faces.append((a, b, b+8, a+8))
    mesh_object(name+'_achenes', verts, faces, mats['seed'], root, collection)
    for i in range(7):
        sep = leaf('calyx', (0, -.030, 0), .023, .005, 2*math.pi*i/7, mats, root, collection)
        sep.rotation_euler = (math.pi/2+.3*math.sin(i), 2*math.pi*i/7, 0)
    return root


def _copy_tree(obj, parent, collection):
    """A copy of an object and everything under it, sharing the mesh and curve data."""
    new = obj.copy()
    collection.objects.link(new)
    new.parent = parent
    new.matrix_parent_inverse = obj.matrix_parent_inverse.copy()
    for child in obj.children:
        _copy_tree(child, new, collection)
    return new


# ---- the renderer -----------------------------------------------------------------


class GreenhouseRenderer:
    """One Blender scene, reused for many images: the greenhouse stays, the plants change."""

    PROTOTYPES = 3  # berry shapes to choose from

    def __init__(self, samples: int = 32, seed: int = 0):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = self.scene = bpy.context.scene
        scene.render.engine = 'CYCLES'
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'OPTIX'
        prefs.get_devices()
        gpu = False
        for device in prefs.devices:
            device.use = device.type == 'OPTIX'
            gpu |= device.use
        scene.cycles.device = 'GPU' if gpu else 'CPU'
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.seed = seed
        scene.cycles.max_bounces = 6
        scene.render.use_persistent_data = True
        scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.film_transparent = False
        scene.render.use_motion_blur = False
        scene.view_settings.view_transform = 'AgX'
        scene.view_settings.look = 'AgX - Medium High Contrast'
        scene.view_settings.exposure = -.25
        scene.world = bpy.data.worlds.new('diffuse greenhouse sky')
        scene.world.use_nodes = True
        scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.65, .75, .9, 1)
        scene.world.node_tree.nodes['Background'].inputs[1].default_value = .2

        # Pinhole camera looking along +z with up = -y; FOCAL_PX pixels of focal length.
        bpy.ops.object.camera_add(location=CAMERA_AT, rotation=(math.pi, 0, 0))
        self.camera = bpy.context.object
        self.camera.data.type = 'PERSP'
        self.camera.data.sensor_fit = 'HORIZONTAL'
        self.camera.data.sensor_width = 36
        self.camera.data.lens = FOCAL_PX*36/WIDTH
        self.camera.data.clip_start, self.camera.data.clip_end = .005, MAX_DEPTH_M
        self.camera.data.dof.use_dof = False
        scene.camera = self.camera

        # Depth and berry index come out of the compositor as EXR files.
        view_layer = scene.view_layers[0]
        view_layer.use_pass_z = True
        view_layer.use_pass_object_index = True
        scene.use_nodes = True
        nodes = scene.node_tree.nodes
        nodes.clear()
        layers = nodes.new('CompositorNodeRLayers')
        scene.node_tree.links.new(layers.outputs['Image'], nodes.new('CompositorNodeComposite').inputs[0])
        for name, socket in (('depth_', 'Depth'), ('index_', 'IndexOB')):
            out = nodes.new('CompositorNodeOutputFile')
            out.name = name
            out.format.file_format = 'OPEN_EXR'
            out.format.color_depth = '32'
            out.file_slots[0].path = name
            scene.node_tree.links.new(layers.outputs[socket], out.inputs[0])

        self.mats = {
            'fruit': material('strawberry skin', (.48, .012, .018), .27, organic=True),
            'seed': material('golden recessed achenes', (.42, .24, .065), .46),
            'leaf': material('leaf tissue', (.035, .18, .017), .48, organic=True),
            'vein': material('leaf veins', (.09, .23, .035), .55),
            'stem': material('peduncle', (.09, .25, .025), .52, organic=True),
            'metal': material('brushed stainless steel', (.5, .54, .58), .27, .92),
            'gutter': material('white hydroponic gutter', (.72, .73, .68), .45),
            'soil': material('growing medium', (.05, .026, .013), .95, organic=True),
        }
        self.lights = []
        for location, power, size in [((-.35, -.6, -.15), 8, .65), ((.4, -.1, .15), 3, .4)]:
            bpy.ops.object.light_add(type='AREA', location=location)
            light = bpy.context.object
            light.data.energy = power
            light.data.shape = 'DISK'
            light.data.size = size
            light.rotation_euler = (mathutils.Vector((0, 0, .6))-light.location).to_track_quat('-Z', 'Y').to_euler()
            self.lights.append((light, power))
        # Fixed metric scene, with visible ground and structural depth references.
        box('growing gutter', (0, -.065, .78), (1.5, .08, .18), self.mats['gutter'], .008)
        box('soil bed', (0, -.108, .78), (1.48, .009, .15), self.mats['soil'], .002)
        box('greenhouse floor', (0, .45, 1.8), (5, .03, 5), self.mats['gutter'], .001)
        box('rear wall', (0, 0, 3), (5, 4, .02), self.mats['gutter'], .001)
        for x in [-.8, -.4, 0, .4, .8]:
            tube('greenhouse column', [(x, -1.2, 1.4), (x, .45, 1.4)], .009, self.mats['metal'])
            tube('greenhouse roof brace', [(x, -1.2, 1.4), (x, -.9, .4)], .008, self.mats['metal'])
        # A second planted row breaks up the industrial backdrop and gives distance structure.
        box('rear planted gutter', (0, .12, 1.4), (2, .06, .20), self.mats['gutter'], .006)
        rng = np.random.default_rng(seed)
        for i in range(22):
            origin = (rng.uniform(-.8, .8), rng.uniform(.04, .09), rng.uniform(1.25, 1.40))
            leaf('rear row foliage', origin, rng.uniform(.09, .15), rng.uniform(.03, .05), rng.uniform(-2.5, 2.5), self.mats)
        for y in [-.4, .25]:
            tube('horizontal frame rail', [(-1.5, y, 1.5), (1.5, y, 1.5)], .008, self.mats['metal'])

        # Berry prototypes, built once and copied for every berry; not rendered themselves.
        prototypes = bpy.data.collections.new('prototypes')
        scene.collection.children.link(prototypes)
        view_layer.layer_collection.children['prototypes'].exclude = True
        self.prototypes = [berry_prototype(f'berry shape {k}', self.mats, 41 + k, prototypes)
                           for k in range(self.PROTOTYPES)]

        # Everything that changes between images lives here and is cleared each time.
        self.plants = bpy.data.collections.new('plants')
        scene.collection.children.link(self.plants)

    def _clear_plants(self):
        for obj in list(self.plants.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for block in (bpy.data.meshes, bpy.data.curves):
            for item in list(block):
                if item.users == 0:
                    block.remove(item)
        for mat in list(bpy.data.materials):  # the per-berry colours of the last image
            if mat.name.startswith(('skin ', 'achenes ')):
                bpy.data.materials.remove(mat)

    def _add_berry(self, index: int, berry: Berry):
        root = _copy_tree(self.prototypes[berry.shape % self.PROTOTYPES], None, self.plants)
        root.location = (berry.x, berry.y, berry.z)
        root.scale = (berry.scale,) * 3
        root.rotation_euler = (0, np.random.default_rng(index).uniform(0, 2*math.pi), 0)
        skin = material(f'skin {index}', berry_color(berry.ripeness), .27, organic=True)
        seeds = material(f'achenes {index}', achene_color(berry.ripeness), .46)
        stack = [root]
        while stack:
            obj = stack.pop()
            stack.extend(obj.children)
            if obj.name.split('.')[0].endswith(('_flesh', '_achenes')):
                obj.pass_index = index  # the mask reports this number for the fruit's pixels
                obj.material_slots[0].link = 'OBJECT'
                obj.material_slots[0].material = skin if '_flesh' in obj.name else seeds
        # The peduncle, from the plant down to the top of the calyx.
        top = np.array(berry.top)
        # By default it comes over the front edge of the gutter.
        attach = np.array(berry.stem_top or (berry.x + .012, -.11, .70))
        middle = (top + attach) / 2 + [.004, .03, -.02]
        tube(f'stem {index}', [attach, middle, top], .0012, self.mats['stem'], collection=self.plants)

    def render(self, berries: list[Berry], rgb_path: pathlib.Path, depth_path: pathlib.Path,
               seed: int = 0, camera_at=CAMERA_AT, leaves_in_front: int = 0) -> np.ndarray:
        """Render these berries; returns the berry index of every pixel (0 = none).

        Berry i in the list is labelled i + 1. `seed` varies the leaves and the
        light; `leaves_in_front` adds leaves between the camera and the fruit.
        """
        rng = np.random.default_rng(seed)
        self._clear_plants()
        self.scene.cycles.seed = seed
        self.camera.location = camera_at
        for light, power in self.lights:
            light.data.energy = power * rng.uniform(.6, 1.5)
        self.scene.view_settings.exposure = -.25 + rng.uniform(-.3, .3)
        for i, berry in enumerate(berries, start=1):
            self._add_berry(i, berry)
        for _ in range(20):  # the plants' foliage, behind and around the fruit
            origin = (rng.uniform(-.32, .32), rng.uniform(-.12, -.04), rng.uniform(.64, .76))
            leaf('serrated strawberry leaf', origin, rng.uniform(.07, .13), rng.uniform(.025, .044),
                 rng.uniform(-2.5, 2.5), self.mats, collection=self.plants)
            tube('leaf petiole', [(origin[0], -.11, .77), origin], .0012, self.mats['stem'], collection=self.plants)
        for _ in range(leaves_in_front):
            origin = (rng.uniform(-.12, .2), rng.uniform(-.04, .12), rng.uniform(.36, .44))
            leaf('front leaf', origin, rng.uniform(.06, .11), rng.uniform(.025, .04), rng.uniform(-2.5, 2.5),
                 self.mats, collection=self.plants)
            tube('leaf petiole', [(origin[0], -.11, .70), origin], .0012, self.mats['stem'], collection=self.plants)

        with tempfile.TemporaryDirectory() as tmp:
            for name in ('depth_', 'index_'):
                self.scene.node_tree.nodes[name].base_path = tmp
            self.scene.render.filepath = str(pathlib.Path(rgb_path).resolve())
            bpy.ops.render.render(write_still=True)
            depth = _read_exr(pathlib.Path(tmp) / 'depth_0001.exr')
            index = _read_exr(pathlib.Path(tmp) / 'index_0001.exr')
        # In this Cycles build the Z pass is axial depth (checked against ray casts in the first version).
        valid = np.isfinite(depth) & (depth > 0) & (depth < MAX_DEPTH_M)
        pil_image.fromarray(np.where(valid, np.rint(depth*1000), 0).astype(np.uint16)).save(depth_path)
        return np.rint(index).astype(np.int32)


def _read_exr(path: pathlib.Path) -> np.ndarray:
    with OpenEXR.File(str(path), separate_channels=True) as exr:
        return exr.channels()['R'].pixels.copy()
