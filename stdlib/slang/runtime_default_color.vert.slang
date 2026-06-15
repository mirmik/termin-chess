struct CameraUBO
{
    float4x4 view;
    float4x4 proj;
    float4x4 view_proj;
    float4 camera_pos;
};

ConstantBuffer<CameraUBO> u_camera;

struct PushConstants
{
    float4x4 model;
};

ConstantBuffer<PushConstants> u_push;

struct VertexInput
{
    float3 position : POSITION;

    float3 color : COLOR0;
};

struct VertexOutput
{
    float3 color : COLOR0;

    float4 position : SV_Position;
};

[shader("vertex")]
VertexOutput main(VertexInput input)
{
    VertexOutput output;
    output.color = input.color;
    output.position = mul(u_camera.view_proj, mul(u_push.model, float4(input.position, 1.0)));
    return output;
}
