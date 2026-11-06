"""Run inside Blender Python. Adapt mapping to the actual rig's shape key names.
Example: exec(open('/path/to/blender_adapter.py').read()); apply_frame(bpy.context.object, channels)
"""
CHANNEL_TO_SHAPEKEY={
 'eye.blink.L':'eyeBlinkLeft','eye.blink.R':'eyeBlinkRight',
 'brow.raise.L':'browOuterUpLeft','brow.raise.R':'browOuterUpRight',
 'brow.furrow':'browDownLeft','cheek.raise.L':'cheekSquintLeft',
 'cheek.raise.R':'cheekSquintRight','jaw.open':'jawOpen',
 'lip.round':'mouthFunnel','lip.spread':'mouthStretchLeft',
 'lip.close':'mouthClose','lip.smile.L':'mouthSmileLeft',
 'lip.smile.R':'mouthSmileRight',
}
def apply_frame(mesh,channels,frame=None):
    keys=getattr(getattr(mesh.data,'shape_keys',None),'key_blocks',None)
    if keys is None:raise ValueError('Mesh has no shape keys')
    missing=[]
    for channel,key_name in CHANNEL_TO_SHAPEKEY.items():
        if key_name not in keys:missing.append(key_name);continue
        key=keys[key_name];key.value=channels.get(channel,0.0)
        if frame is not None:key.keyframe_insert(data_path='value',frame=frame)
    return {'missing_shape_keys':missing}
