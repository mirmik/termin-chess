// Bloom downsample pass — 13-tap box filter for mip chain.
//

import termin_prelude;

struct BloomDownsampleParams {
    float2 texel_size;
};

[[TerminScope("draw")]]
ConstantBuffer<BloomDownsampleParams> u_params;

[[TerminScope("transient")]]
Sampler2D u_texture;

struct FragmentInput {
    float2 uv : TEXCOORD0;
};

struct FragmentOutput {
    float4 color : SV_Target0;
};

[shader("fragment")]
FragmentOutput fs_main(FragmentInput input) {
    float2 ts = u_params.texel_size;
    float3 a = u_texture.Sample(input.uv + float2(-2.0, -2.0) * ts).rgb;
    float3 b = u_texture.Sample(input.uv + float2( 0.0, -2.0) * ts).rgb;
    float3 c = u_texture.Sample(input.uv + float2( 2.0, -2.0) * ts).rgb;
    float3 d = u_texture.Sample(input.uv + float2(-2.0,  0.0) * ts).rgb;
    float3 e = u_texture.Sample(input.uv + float2( 0.0,  0.0) * ts).rgb;
    float3 f = u_texture.Sample(input.uv + float2( 2.0,  0.0) * ts).rgb;
    float3 g = u_texture.Sample(input.uv + float2(-2.0,  2.0) * ts).rgb;
    float3 h = u_texture.Sample(input.uv + float2( 0.0,  2.0) * ts).rgb;
    float3 i = u_texture.Sample(input.uv + float2( 2.0,  2.0) * ts).rgb;
    float3 j = u_texture.Sample(input.uv + float2(-1.0, -1.0) * ts).rgb;
    float3 k = u_texture.Sample(input.uv + float2( 1.0, -1.0) * ts).rgb;
    float3 l = u_texture.Sample(input.uv + float2(-1.0,  1.0) * ts).rgb;
    float3 m = u_texture.Sample(input.uv + float2( 1.0,  1.0) * ts).rgb;
    float3 result = e * 0.125;
    result += (a + c + g + i) * 0.03125;
    result += (b + d + f + h) * 0.0625;
    result += (j + k + l + m) * 0.125;

    FragmentOutput output;
    output.color = float4(result, 1.0);
    return output;
}
