import termin_prelude;

struct PerFrame {
    column_major float4x4 u_view;
    column_major float4x4 u_projection;
};

[[TerminScope("frame")]]
ConstantBuffer<PerFrame> per_frame;

struct ShadowPushData {
    column_major float4x4 u_model;
};

[[TerminScope("draw")]]
ConstantBuffer<ShadowPushData> shadow_draw;

struct VertexInput {
    float3 position : POSITION;
};

struct VertexOutput {
    float4 position : SV_Position;
};

[shader("vertex")]
VertexOutput vs_main(VertexInput input) {
    VertexOutput output;
    float4 world_pos = mul(shadow_draw.u_model, float4(input.position, 1.0));
    output.position = mul(per_frame.u_projection, mul(per_frame.u_view, world_pos));
    return output;
}

[shader("fragment")]
void fs_main() {
}
