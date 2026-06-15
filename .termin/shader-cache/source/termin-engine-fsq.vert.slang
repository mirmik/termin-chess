struct VertexInput
{
    float2 position : POSITION;

    float2 uv : TEXCOORD0;
};

struct VertexOutput
{
    float4 position : SV_Position;

    float2 uv : TEXCOORD0;
};

[shader("vertex")]
VertexOutput vs_main(VertexInput input)
{
    VertexOutput output;
    output.position = float4(input.position, 0.0, 1.0);
    output.uv = input.uv;
    return output;
}
