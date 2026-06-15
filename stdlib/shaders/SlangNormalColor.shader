@program SlangNormalColor
@language slang

@phase opaque
@priority 0
@glDepthTest true
@glDepthMask true
@glCull true

@stage vertex
import termin_prelude;

struct PerFrame
{
    column_major float4x4 u_view;
    column_major float4x4 u_projection;
    column_major float4x4 u_view_projection;
    column_major float4x4 u_inv_view;
    column_major float4x4 u_inv_proj;
    float4 u_camera_position;
    float2 u_resolution;
    float u_near;
    float u_far;
};

[[TerminScope("frame")]]
ConstantBuffer<PerFrame> per_frame;

struct SlangDrawData
{
    column_major float4x4 u_model;
};

[[TerminScope("draw")]]
ConstantBuffer<SlangDrawData> draw_data;

struct VertexInput
{
    float3 position : POSITION;
    float3 normal : NORMAL;
};

struct VertexOutput
{
    float4 position : SV_Position;
    float3 normal_world : NORMAL;
};

[shader("vertex")]
VertexOutput main(VertexInput input)
{
    VertexOutput output;
    float4 world = mul(draw_data.u_model, float4(input.position, 1.0));
    output.position = mul(per_frame.u_projection, mul(per_frame.u_view, world));
    output.normal_world = mul((float3x3)draw_data.u_model, input.normal);
    return output;
}
@endstage

@stage fragment
struct FragmentInput
{
    float3 normal_world : NORMAL;
};

struct FragmentOutput
{
    float4 color : SV_Target0;
};

[shader("fragment")]
FragmentOutput main(FragmentInput input)
{
    FragmentOutput output;
    float3 n = normalize(input.normal_world);
    output.color = float4(n * 0.5 + 0.5, 1.0);
    return output;
}
@endstage
