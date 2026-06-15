struct FragmentInput
{
    float3 color : COLOR0;
};

struct FragmentOutput
{
    float4 color : SV_Target0;
};

[shader("fragment")]
FragmentOutput main(FragmentInput input)
{
    FragmentOutput output;
    output.color = float4(input.color, 1.0);
    return output;
}
