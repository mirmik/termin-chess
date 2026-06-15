#version 450 core
layout(std140, binding = 1) uniform MaterialParams {
    mat4 u_view;
    mat4 u_projection;
    int u_skybox_type;
    vec4 u_skybox_color;
    vec4 u_skybox_top_color;
    vec4 u_skybox_bottom_color;
};
layout(location = 0) in vec3 a_position;


layout(location = 0) out vec3 v_dir;

void main() {
    mat4 view_no_translation = mat4(mat3(u_view));
    v_dir = a_position;
    gl_Position = u_projection * view_no_translation * vec4(a_position, 1.0);
}
