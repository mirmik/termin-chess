import termin_prelude;

struct PerFrame {
    column_major float4x4 u_view;
    column_major float4x4 u_projection;
    float u_near;
    float u_far;
    float u_depth_encoding;
};

[[TerminScope("frame")]]
ConstantBuffer<PerFrame> per_frame;

struct DepthPushData {
    column_major float4x4 u_model;
};

[[TerminScope("draw")]]
ConstantBuffer<DepthPushData> depth_draw;

struct VertexInput {
    float3 position : POSITION;
};

struct VertexOutput {
    float4 position : SV_Position;
    float linear_depth : TEXCOORD0;
    float perspective_depth : TEXCOORD1;
    float log_depth : TEXCOORD2;
};

[shader("vertex")]
VertexOutput vs_main(VertexInput input) {
    VertexOutput output;
    float4 world_pos = mul(depth_draw.u_model, float4(input.position, 1.0));
    float4 view_pos = mul(per_frame.u_view, world_pos);

    float view_depth = view_pos.y;
    float depth = (view_depth - per_frame.u_near) / (per_frame.u_far - per_frame.u_near);

    float4 clip_pos = mul(per_frame.u_projection, view_pos);
    float ndc_depth = clip_pos.z / max(abs(clip_pos.w), 1.0e-6);

    output.position = clip_pos;
    output.linear_depth = depth;
    output.perspective_depth = ndc_depth;
    output.log_depth =
        log2(max(view_depth, 0.0) + 1.0) /
        log2(max(per_frame.u_far, 1.0e-6) + 1.0);
    return output;
}

struct FragmentInput {
    float linear_depth : TEXCOORD0;
    float perspective_depth : TEXCOORD1;
    float log_depth : TEXCOORD2;
};

struct FragmentOutput {
    float4 color : SV_Target0;
};

[shader("fragment")]
FragmentOutput fs_main(FragmentInput input) {
    FragmentOutput output;
    int mode = int(per_frame.u_depth_encoding + 0.5);
    float depth = input.linear_depth;
    if (mode == 2 || mode == 3) {
        depth = input.perspective_depth;
    } else if (mode == 4 || mode == 5) {
        depth = input.log_depth;
    }
    depth = clamp(depth, 0.0, 1.0);
    if (mode == 1 || mode == 3 || mode == 5) {
        depth = 1.0 - depth;
    }
    output.color = float4(depth, depth, depth, 1.0);
    return output;
}
