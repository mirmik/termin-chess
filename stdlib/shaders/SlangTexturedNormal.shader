@program SlangTexturedNormal
@language slang

@phase opaque
@priority 0
@glDepthTest true
@glDepthMask true
@glCull true

@property Color u_tint_color = Color(1.0, 1.0, 1.0, 1.0)
@property Texture2D u_tint_texture = "white"

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
    float2 uv : TEXCOORD0;
};

struct VertexOutput
{
    float4 position : SV_Position;
    float3 normal_world : NORMAL;
    float2 uv : TEXCOORD0;
};

[shader("vertex")]
VertexOutput main(VertexInput input)
{
    VertexOutput output;
    float4 world = mul(draw_data.u_model, float4(input.position, 1.0));
    output.position = mul(per_frame.u_projection, mul(per_frame.u_view, world));
    output.normal_world = mul((float3x3)draw_data.u_model, input.normal);
    output.uv = input.uv;
    return output;
}
@endstage

@stage fragment
struct FragmentInput
{
    float3 normal_world : NORMAL;
    float2 uv : TEXCOORD0;
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
    float4 tint = u_tint_texture.Sample(input.uv);
    output.color = float4(n * 0.5 + 0.5, 1.0) * material.u_tint_color * tint;
    return output;
}
@endstage
