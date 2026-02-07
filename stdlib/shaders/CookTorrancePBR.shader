@program CookTorrancePBR
@features lighting_ubo

// ============================================================
// Cook-Torrance PBR Shader
// ============================================================
//
// Physically-based rendering with metallic-roughness workflow.
//
// BRDF: f = kD * (albedo/PI) + (D * G * F) / (4 * NdotV * NdotL)
//
// Components:
//   D - GGX/Trowbridge-Reitz Normal Distribution Function
//   G - Smith's Geometry Function
//   F - Fresnel-Schlick Approximation
//
// Features:
//   - Metallic-Roughness workflow
//   - Subsurface scattering approximation (wrap lighting)
//   - Emission (HDR)
//   - ACES tone mapping
//   - Shadow mapping with cascades
//   - Normal mapping with TBN matrix
//
// TODO: IBL - Image-Based Lighting (environment cubemap)
// TODO: AO map (u_ao_texture) - baked ambient occlusion
// TODO: Metallic/Roughness textures
// TODO: Clearcoat layer
//
// ============================================================

@phases opaque, transparent

@settings transparent
@glDepthMask false
@glBlend true
@glCull true

@property Color u_color = Color(1.0, 1.0, 1.0, 1.0)
@property Float u_metallic = 0.0 range(0.0, 1.0)
@property Float u_roughness = 0.5 range(0.0, 1.0)
@property Float u_subsurface = 0.0 range(0.0, 1.0)
@property Float u_diffuse_mul = 1.0 range(0.1, 10.0)
@property Color u_emission_color = Color(0.0, 0.0, 0.0, 1.0)
@property Float u_emission_intensity = 0.0 range(0.0, 100.0)
@property Texture2D u_albedo_texture = "white"
@property Texture2D u_normal_texture = "normal"
@property Float u_normal_strength = 1.0 range(0.0, 2.0)

@stage vertex
#version 330 core

layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec2 a_uv;
layout(location = 3) in vec4 a_tangent;  // xyz = tangent, w = handedness

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

out vec3 v_world_pos;
out vec3 v_normal;
out vec2 v_uv;
out mat3 v_TBN;
out vec3 v_tangent;

void main() {
    vec4 world = u_model * vec4(a_position, 1.0);
    v_world_pos = world.xyz;

    // Transform normal to world space
    mat3 normal_matrix = transpose(inverse(mat3(u_model)));
    vec3 N = normalize(normal_matrix * a_normal);

    // Check if tangent data is valid (non-zero length)
    float tangent_len = length(a_tangent.xyz);
    if (tangent_len > 0.001) {
        // Transform tangent to world space
        vec3 T = normalize(normal_matrix * a_tangent.xyz);

        // Re-orthogonalize T with respect to N (Gram-Schmidt)
        T = normalize(T - dot(T, N) * N);

        // Bitangent = cross(N, T) * handedness
        vec3 B = cross(N, T) * a_tangent.w;

        // TBN matrix transforms from tangent space to world space
        v_TBN = mat3(T, B, N);
    } else {
        // No tangent data - set TBN to zero matrix (will be detected in fragment shader)
        v_TBN = mat3(0.0);
    }

    v_normal = N;
    v_uv = a_uv;
    v_tangent = a_tangent.xyz;
    gl_Position = u_projection * u_view * world;
}
@endstage

@stage fragment
#version 330 core

in vec3 v_world_pos;
in vec3 v_normal;
in vec2 v_uv;
in mat3 v_TBN;
in vec3 v_tangent;

#include "lighting.glsl"
#include "shadows.glsl"

// Material parameters
uniform vec4 u_color;
uniform sampler2D u_albedo_texture;
uniform sampler2D u_normal_texture;
uniform float u_normal_strength;
uniform float u_metallic;
uniform float u_roughness;
uniform float u_subsurface;
uniform float u_diffuse_mul;

// Emission
uniform vec4 u_emission_color;
uniform float u_emission_intensity;

out vec4 FragColor;

const float PI = 3.14159265359;

// ============== PBR Functions ==============

// Normal Distribution Function (GGX/Trowbridge-Reitz)
// Models microfacet distribution on the surface
float D_GGX(float NdotH, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float denom = NdotH * NdotH * (a2 - 1.0) + 1.0;
    return a2 / (PI * denom * denom);
}

// Geometry Function (Smith's method with GGX)
// Models microfacet self-shadowing
float G_Smith(float NdotV, float NdotL, float roughness) {
    float r = roughness + 1.0;
    float k = (r * r) / 8.0;
    float G1_V = NdotV / (NdotV * (1.0 - k) + k);
    float G1_L = NdotL / (NdotL * (1.0 - k) + k);
    return G1_V * G1_L;
}

// Fresnel (Schlick approximation)
// Models increased reflectance at grazing angles
vec3 F_Schlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

// ============== SSS Approximation ==============

// Wrap lighting: softens the terminator
float wrap_diffuse(float NdotL, float wrap) {
    return max(0.0, (NdotL + wrap) / (1.0 + wrap));
}

// Subsurface color shift (warm tones for skin)
vec3 subsurface_color(vec3 albedo) {
    return albedo * vec3(1.0, 0.4, 0.25);
}

// ============== Normal Mapping ==============

vec3 get_normal_from_map() {
    // Sample normal map (stored in tangent space)
    vec3 normal_sample = texture(u_normal_texture, v_uv).rgb;

    // Convert from [0,1] to [-1,1] range
    vec3 tangent_normal = normal_sample * 2.0 - 1.0;

    // Apply normal strength (blend between (0,0,1) and sampled normal)
    tangent_normal.xy *= u_normal_strength;
    tangent_normal = normalize(tangent_normal);

    // Transform from tangent space to world space using TBN matrix
    return normalize(v_TBN * tangent_normal);
}

// ============== Main ==============

void main() {
    // Get normal from normal map if available, otherwise use vertex normal
    // Note: If mesh has no tangents, v_TBN will be invalid - we detect this
    // by checking if the TBN columns are valid (non-zero length)
    vec3 N;
    float tbn_valid = length(v_TBN[0]) * length(v_TBN[1]) * length(v_TBN[2]);
    if (tbn_valid > 0.001 && u_normal_strength > 0.0) {
        N = get_normal_from_map();
    } else {
        N = normalize(v_normal);
    }

    vec3 V = normalize(get_camera_position() - v_world_pos);

    // // DEBUG
    // vec3 normals_by_map = texture(u_normal_texture, v_uv).rgb;
    // vec3 bitangent = normalize(v_TBN[1]);
    // vec3 normal = normalize(v_TBN[2]);
    // //FragColor = vec4(normals_by_map, 1.0);
    // FragColor = vec4(v_tangent * 0.5 + 0.5, 1.0);
    // return;
    // // DEBUG

    // Sample albedo
    vec4 tex_color = texture(u_albedo_texture, v_uv);
    vec3 albedo = u_color.rgb * tex_color.rgb;
    float alpha = u_color.a * tex_color.a;

    float metallic = u_metallic;
    float roughness = max(u_roughness, 0.04);
    float subsurface = u_subsurface;

    // F0: reflectance at normal incidence
    // Dielectrics ~0.04, metals use albedo
    vec3 F0 = mix(vec3(0.04), albedo, metallic);

    // Ambient term
    // TODO: Replace with IBL (irradiance map)
    vec3 ambient = get_ambient_color() * get_ambient_intensity() * albedo * (1.0 - metallic * 0.5);

    vec3 Lo = vec3(0.0);

    for (int i = 0; i < get_light_count(); ++i) {
        vec3 L;
        float attenuation = 1.0;

        if (get_light_type(i) == LIGHT_TYPE_DIRECTIONAL) {
            L = normalize(-get_light_direction(i));
        } else {
            vec3 to_light = get_light_position(i) - v_world_pos;
            float dist = length(to_light);
            L = to_light / max(dist, 0.0001);
            attenuation = compute_distance_attenuation(get_light_attenuation(i), get_light_range(i), dist);

            if (get_light_type(i) == LIGHT_TYPE_SPOT) {
                attenuation *= compute_spot_weight(get_light_direction(i), L, get_light_inner_angle(i), get_light_outer_angle(i));
            }
        }

        vec3 H = normalize(V + L);

        float NdotL_raw = dot(N, L);
        float NdotL = max(NdotL_raw, 0.0);
        float NdotV = max(dot(N, V), 0.001);
        float NdotH = max(dot(N, H), 0.0);
        float HdotV = max(dot(H, V), 0.0);

        // Cook-Torrance specular BRDF
        float D = D_GGX(NdotH, roughness);
        float G = G_Smith(NdotV, NdotL, roughness);
        vec3 F = F_Schlick(HdotV, F0);

        vec3 numerator = D * G * F;
        float denominator = 4.0 * NdotV * NdotL + 0.0001;
        vec3 specular = numerator / denominator;

        // Diffuse with energy conservation
        // Metals have no diffuse, energy reflected = F
        vec3 kD = (1.0 - F) * (1.0 - metallic);

        // Standard Lambertian diffuse
        vec3 diffuse_standard = kD * albedo / PI * u_diffuse_mul;

        // SSS: wrap lighting + color shift
        float wrap_amount = subsurface * 0.5;
        float diffuse_wrap = wrap_diffuse(NdotL_raw, wrap_amount);
        vec3 sss_color = subsurface_color(albedo);

        float sss_mask = max(0.0, diffuse_wrap - NdotL) * 2.0;
        vec3 diffuse_sss = kD * mix(albedo, sss_color, sss_mask * subsurface) / PI * u_diffuse_mul;

        // Blend standard and SSS diffuse
        vec3 diffuse_final = mix(diffuse_standard * NdotL, diffuse_sss * diffuse_wrap, subsurface);

        // Shadow
        float shadow = 1.0;
        if (get_light_type(i) == LIGHT_TYPE_DIRECTIONAL) {
            shadow = compute_shadow_auto(i);
        }

        // Combine
        vec3 radiance = get_light_color(i) * get_light_intensity(i) * attenuation;
        Lo += (diffuse_final + specular * NdotL) * radiance * shadow;
    }

    vec3 color = ambient + Lo;

    // Emission (HDR - will be tonemapped in post-process)
    color += u_emission_color.rgb * u_emission_intensity;

    FragColor = vec4(color, alpha);
}
@endstage

// ============================================================
// Shadow caster phase
// ============================================================

@phase shadow
@priority 0
@glDepthTest true
@glDepthMask true
@glCull true

@stage vertex
#version 330 core

layout(location = 0) in vec3 a_position;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

void main() {
    gl_Position = u_projection * u_view * u_model * vec4(a_position, 1.0);
}
@endstage

@stage fragment
#version 330 core

out vec4 FragColor;

void main() {
    FragColor = vec4(gl_FragCoord.z, 0.0, 0.0, 1.0);
}
@endstage

@endphase
