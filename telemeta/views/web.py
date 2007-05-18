# Copyright (C) 2007 Samalyse SARL
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://svn.parisson.org/telemeta/TelemetaLicense.
#
# Author: Olivier Guilyardi <olivier@samalyse.com>

import telemeta
from django.template import Context, loader
from django import template
from django.http import HttpResponse
from django.http import Http404
from telemeta.models import MediaItem
from telemeta.models import MediaCollection
from django.shortcuts import render_to_response
import re
from telemeta.core import *
from telemeta.export import *
from telemeta.visualization import *
from django.conf import settings
import os

class WebView(Component):
    """Provide web UI methods"""

    exporters = ExtensionPoint(IExporter)
    visualizers = ExtensionPoint(IMediaItemVisualizer)

    def index(self, request):
        """Render the homepage"""

        template = loader.get_template('index.html')
        context = Context({})
        return HttpResponse(template.render(context))

    def item_detail(self, request, item_id, template='mediaitem_detail.html'):
        """Show the details of a given item"""
        item = MediaItem.objects.get(pk=item_id)
        formats = []
        for exporter in self.exporters:
            formats.append(exporter.get_format())
        visualizers = []
        for visualizer in self.visualizers:
            visualizers.append({'name':visualizer.get_name(), 'id': 
                visualizer.get_id()})
        if request.REQUEST.has_key('visualizer_id'):
            visualizer_id = request.REQUEST['visualizer_id']
        else:
            visualizer_id = 'waveform'

        return render_to_response(template, 
                    {'item': item, 'export_formats': formats, 
                    'visualizers': visualizers, 'visualizer_id': visualizer_id})
                    
    def item_visualize(self, request, item_id, visualizer_id):
        for visualizer in self.visualizers:
            if visualizer.get_id() == visualizer_id:
                break

        if visualizer.get_id() != visualizer_id:
            raise Http404
        
        item = MediaItem.objects.get(pk=item_id)

        stream = visualizer.render(item)
        response = HttpResponse(stream, mimetype = 'image/png')
        return response

    def item_export(self, request, item_id, format):                    
        """Export a given media item in the specified format (OGG, FLAC, ...)"""
        for exporter in self.exporters:
            if exporter.get_format() == format:
                break

        if exporter.get_format() != format:
            raise Http404

        mime_type = exporter.get_mime_type()

        exporter.set_cache_dir(settings.TELEMETA_EXPORT_CACHE_DIR)

        item = MediaItem.objects.get(pk=item_id)

        infile = settings.MEDIA_ROOT + "/" + item.file
        metadata = item.to_dublincore().flatten()
        stream = exporter.process(item.id, infile, metadata)

        response = HttpResponse(stream, mimetype = mime_type)
        response['Content-Disposition'] = 'attachment; filename="download.' + \
                    exporter.get_file_extension() + '"'
        return response

    def quick_search(self, request):
        """Perform a simple search through collections and items core metadata"""
        pattern = request.REQUEST["pattern"]
        collections = MediaCollection.objects.quick_search(pattern)
        items = MediaItem.objects.quick_search(pattern)
        return render_to_response('search_results.html', 
                    {'pattern': pattern, 'collections': collections, 
                     'items': items})

    def __get_enumerations_list(self):
        from django.db.models import get_models
        models = get_models(telemeta.models)

        enumerations = []
        for model in models:
            if getattr(model, "is_enumeration", False):
                enumerations.append({"name": model._meta.verbose_name_plural, 
                    "id": model._meta.module_name})
        return enumerations                    
    
    def __get_admin_context_vars(self):
        return {"enumerations": self.__get_enumerations_list()}

    def admin_index(self, request):
        return render_to_response('admin.html', self. __get_admin_context_vars())

    def __get_enumeration(self, id):
        from django.db.models import get_models
        models = get_models(telemeta.models)
        for model in models:
            if model._meta.module_name == id:
                break

        if model._meta.module_name != id:
            return None

        return model

    def edit_enumeration(self, request, enumeration_id):        

        enumeration  = self.__get_enumeration(enumeration_id)
        if enumeration == None:
            raise Http404

        vars = self.__get_admin_context_vars()
        vars["enumeration_id"] = enumeration._meta.module_name
        vars["enumeration_name"] = enumeration._meta.verbose_name            
        vars["enumeration_name_plural"] = enumeration._meta.verbose_name_plural
        vars["enumeration_values"] = enumeration.objects.all()
        return render_to_response('enumeration_edit.html', vars)

    def add_to_enumeration(self, request, enumeration_id):        

        enumeration  = self.__get_enumeration(enumeration_id)
        if enumeration == None:
            raise Http404

        enumeration_value = enumeration(value=request.POST['value'])
        enumeration_value.save()

        return self.edit_enumeration(request, enumeration_id)

    def update_enumeration(self, request, enumeration_id):        
        
        enumeration  = self.__get_enumeration(enumeration_id)
        if enumeration == None:
            raise Http404

        if request.POST.has_key("remove"):
            enumeration.objects.filter(id__in=request.POST.getlist('sel')).delete()

        return self.edit_enumeration(request, enumeration_id)

    def edit_enumeration_value(self, request, enumeration_id, value_id):        

        enumeration  = self.__get_enumeration(enumeration_id)
        if enumeration == None:
            raise Http404
        
        vars = self.__get_admin_context_vars()
        vars["enumeration_id"] = enumeration._meta.module_name
        vars["enumeration_name"] = enumeration._meta.verbose_name            
        vars["enumeration_name_plural"] = enumeration._meta.verbose_name_plural
        vars["enumeration_record"] = enumeration.objects.get(id__exact=value_id)
        return render_to_response('enumeration_edit_value.html', vars)

    def update_enumeration_value(self, request, enumeration_id, value_id):        

        if request.POST.has_key("save"):
            enumeration  = self.__get_enumeration(enumeration_id)
            if enumeration == None:
                raise Http404
       
            record = enumeration.objects.get(id__exact=value_id)
            record.value = request.POST["value"]
            record.save()

        return self.edit_enumeration(request, enumeration_id)
  
    def collection_playlist(self, request, collection_id, template, mimetype):
        collection = MediaCollection.objects.get(id__exact=collection_id)
        if not collection:
            raise Http404

        template = loader.get_template(template)
        context = Context({'collection': collection, 'host': request.META['HTTP_HOST']})
        return HttpResponse(template.render(context), mimetype=mimetype)

    def item_playlist(self, request, item_id, template, mimetype):
        item = MediaItem.objects.get(id__exact=item_id)
        if not item:
            raise Http404

        template = loader.get_template(template)
        context = Context({'item': item, 'host': request.META['HTTP_HOST']})
        return HttpResponse(template.render(context), mimetype=mimetype)

        
    
    

    
