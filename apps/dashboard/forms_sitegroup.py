from django import forms
from .models import SiteGroup, SiteGroupHostname


class SiteGroupForm(forms.ModelForm):
    class Meta:
        model = SiteGroup
        fields = ['name', 'slug', 'description', 'site_name', 'site_icon', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 rounded px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 transition',
            }),
            'slug': forms.TextInput(attrs={
                'class': 'w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 rounded px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 transition',
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 rounded px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 transition',
                'rows': 3,
            }),
            'site_name': forms.TextInput(attrs={
                'class': 'w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 rounded px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 transition',
            }),
            'site_icon': forms.TextInput(attrs={
                'class': 'w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 rounded px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 transition',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 bg-slate-900/50 border-slate-700/50 rounded focus:ring-cyan-500/50 text-cyan-500',
            }),
        }


class SiteGroupHostnameForm(forms.ModelForm):
    class Meta:
        model = SiteGroupHostname
        fields = ['hostname']
        widgets = {
            'hostname': forms.TextInput(attrs={
                'class': 'w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 rounded px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 transition',
                'placeholder': 'demo.example.com',
            }),
        }
