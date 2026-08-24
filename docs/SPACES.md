# Spaces

Spaces is the future higher-level creative workflow canvas. It will use React Flow, but it is not intended to reproduce raw ComfyUI graphs.

## Implemented foundation

- Typed workflow JSON models for nodes, edges, positions, and node data
- SQLite workflow persistence and `GET/POST /api/workflows`
- Unique-node and connection validation
- Missing-node, self-connection, and cycle rejection
- Version field for future workflow migrations
- A clearly non-interactive product preview in the UI

The canvas remains disabled until Simple Mode T2V works with an actual H3 workflow.

## Planned node contract

Nodes expose semantic typed ports such as image, video, audio, text prompt, seed, and configuration. Planned initial families are:

- Inputs: Image, Video, Audio, Prompt, Seed
- H3: Text to Video, Image to Video, Reference to Video
- Utilities: Extract First/Last Frame, Trim, Crop, Resize
- Post-processing: Upscale Video, Frame Interpolation
- Outputs: Video Preview, Save Video, Export

React Flow state serializes to this shape:

```json
{
  "version": 1,
  "nodes": [
    { "id": "prompt-1", "type": "prompt", "position": { "x": 80, "y": 120 }, "data": {} }
  ],
  "edges": []
}
```

## Execution and caching

The backend compiler will translate a validated Spaces DAG into application jobs, not a one-to-one visual copy of ComfyUI nodes. Every executable node should calculate a cache key from:

- node type and implementation version
- normalized parameters
- upstream output content hashes
- provider/model/workflow revision

`Run Node` and `Run From Here` can then reuse unchanged upstream artifacts. If a user changes only upscale settings, the existing H3 output remains addressable and only the post-processing node reruns.

Built-in templates will be ordinary versioned workflow JSON. They should include T2V, I2V, character reference, reference + 1080p, and full-quality pipelines once the underlying adapters are verified.

