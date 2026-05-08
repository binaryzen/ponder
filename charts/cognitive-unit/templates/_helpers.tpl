{{/*
Expand the name of the chart.
*/}}
{{- define "cognitive-unit.name" -}}
{{- .Values.unit.name | default .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "cognitive-unit.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
ponder/unit: {{ .Values.unit.name }}
{{- end }}

{{/*
Selector labels for a specific region
*/}}
{{- define "cognitive-unit.regionLabels" -}}
app.kubernetes.io/name: {{ printf "%s-%s" .unit .region | trunc 63 }}
app.kubernetes.io/component: {{ .region }}
ponder/unit: {{ .unit }}
{{- end }}
