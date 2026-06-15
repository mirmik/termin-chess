import termin_prelude;

struct PerFrame {
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
#define u_view per_frame.u_view
#define u_projection per_frame.u_projection
#define u_view_projection per_frame.u_view_projection
#define u_inv_view per_frame.u_inv_view
#define u_inv_proj per_frame.u_inv_proj
#define u_camera_position per_frame.u_camera_position
#define u_resolution per_frame.u_resolution
#define u_near per_frame.u_near
#define u_far per_frame.u_far

struct DrawData {
    column_major float4x4 _u_model;
};
[[TerminScope("draw")]]
ConstantBuffer<DrawData> draw_data;
#define u_model draw_data._u_model
struct VertexInput {
    float3 position : POSITION;
    float3 normal : NORMAL;
    float2 uv : TEXCOORD0;
    float4 tangent : TANGENT;
};

struct VertexOutput {
    float4 position : SV_Position;
    float3 world_pos : TEXCOORD0;
    float3 normal_world : TEXCOORD1;
    float2 uv : TEXCOORD2;
    float3 tangent_world : TEXCOORD3;
    float3 bitangent_world : TEXCOORD4;
    float tbn_valid : TEXCOORD5;
};

[shader("vertex")]
VertexOutput main(VertexInput input) {
    VertexOutput output;
    float4 world = mul(u_model, float4(input.position, 1.0));
    float3x3 normal_matrix = (float3x3)u_model;
    float3 N = normalize(mul(normal_matrix, input.normal));

    output.world_pos = world.xyz;
    output.normal_world = N;
    output.uv = input.uv;
    output.tangent_world = float3(0.0, 0.0, 0.0);
    output.bitangent_world = float3(0.0, 0.0, 0.0);
    output.tbn_valid = 0.0;

    float tangent_len = length(input.tangent.xyz);
    if (tangent_len > 0.001) {
        float3 T = normalize(mul(normal_matrix, input.tangent.xyz));
        T = normalize(T - dot(T, N) * N);
        float3 B = cross(N, T) * input.tangent.w;

        output.tangent_world = T;
        output.bitangent_world = B;
        output.tbn_valid = 1.0;
    }

    output.position = mul(u_projection, mul(u_view, world));
    return output;
}
