// Bloom upsample pass — 9-tap tent filter with blend factor.
//

import termin_prelude;

struct BloomUpsampleParams {
    float2 texel_size;
    float blend_factor;
};

[[TerminScope("draw")]]
ConstantBuffer<BloomUpsampleParams> u_params;

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
    float3 a = u_texture.Sample(input.uv + float2(-1.0, -1.0) * ts).rgb;
    float3 b = u_texture.Sample(input.uv + float2( 0.0, -1.0) * ts).rgb;
    float3 c = u_texture.Sample(input.uv + float2( 1.0, -1.0) * ts).rgb;
    float3 d = u_texture.Sample(input.uv + float2(-1.0,  0.0) * ts).rgb;
    float3 e = u_texture.Sample(input.uv + float2( 0.0,  0.0) * ts).rgb;
    float3 f = u_texture.Sample(input.uv + float2( 1.0,  0.0) * ts).rgb;
    float3 g = u_texture.Sample(input.uv + float2(-1.0,  1.0) * ts).rgb;
    float3 h = u_texture.Sample(input.uv + float2( 0.0,  1.0) * ts).rgb;
    float3 i = u_texture.Sample(input.uv + float2( 1.0,  1.0) * ts).rgb;
    float3 upsampled = e * 4.0;
    upsampled += (b + d + f + h) * 2.0;
    upsampled += (a + c + g + i);
    upsampled /= 16.0;

    FragmentOutput output;
    output.color = float4(upsampled * u_params.blend_factor, 1.0);
    return output;
}
